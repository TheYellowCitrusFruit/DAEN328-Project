import streamlit as st
import sqlite3
import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely import wkt
from sklearn.ensemble import RandomForestRegressor
import folium
from streamlit_folium import st_folium
import branca.colormap as cm
import matplotlib.pyplot as plt
import seaborn as sns
import re
import os

# Set page to wide mode to accommodate the map
st.set_page_config(layout="wide", page_title="NYC Traffic Volume Predictor")

def robust_nyc_clean(street_name):
    if not isinstance(street_name, str):
        return ""
    s = street_name.upper().strip()
    s = re.sub(r'^(?:EB|WB|NB|SB|E/B|W/B|N/B|S/B|APPROACH TO|APPR TO|N/|S/|E/|W/)\s+', '', s)
    s = re.split(r'\s+(?:BTWN|BETWEEN|@|AT|APPROACH TO|APPR TO|AND|&|/)\s+', s)[0]
    s = re.sub(r'\bEAST\b', 'E', s)
    s = re.sub(r'\bWEST\b', 'W', s)
    s = re.sub(r'\bNORTH\b', 'N', s)
    s = re.sub(r'\bSOUTH\b', 'S', s)
    s = re.sub(r'(\d+)(?:ST|ND|RD|TH)', r'\1', s)
    s = re.sub(r'\bAVENUE\b', 'AVE', s)
    s = re.sub(r'\bSTREET\b', 'ST', s)
    s = re.sub(r'\bDRIVE\b', 'DR', s)
    s = re.sub(r'\bBOULEVARD\b', 'BLVD', s)
    s = re.sub(r'\bPARKWAY\b', 'PKWY', s)
    s = re.sub(r'\bROAD\b', 'RD', s)
    s = re.sub(r'\bPLACE\b', 'PL', s)
    return s.strip()

@st.cache_resource
def load_and_train_model():
    """
    Loads data from data/traffic_data.db using the schema:
    - traffic_count: segmentid, hh, day_of_week, is_weekend, vol
    - segment: segmentid, street, wktgeom
    """
    db_path = 'data/traffic_data.db'
    
    if not os.path.exists(db_path):
        st.error(f"Database not found at {db_path}")
        return None, None

    conn = sqlite3.connect(db_path)
    
    try:
        # Load Volume Data from 'traffic_count' table
        traffic_df = pd.read_sql_query(
            """
            SELECT segmentid, hh, day_of_week, is_weekend, vol 
            FROM traffic_count
            """, 
            conn
        )
        traffic_df.columns = ['segmentId', 'hour', 'dayOfWeek', 'isWeekend', 'totalVolume']
        
        # Load Geometry Data from 'segment' table
        geometry_df = pd.read_sql_query(
            "SELECT segmentid, street, wktgeom FROM segment", 
            conn
        )
        geometry_df.columns = ['segmentId', 'street', 'wktGeom']
        
    except Exception as e:
        st.error(f"SQL Query Error: {e}")
        conn.close()
        return None, None

    # Prep Geometry
    unique_roads = geometry_df.drop_duplicates(subset=['segmentId']).copy()
    unique_roads['geometry'] = unique_roads['wktGeom'].apply(wkt.loads)
    sensor_gdf = gpd.GeoDataFrame(unique_roads, geometry='geometry', crs="EPSG:2263")
    sensor_gdf['street_clean'] = sensor_gdf['street'].apply(robust_nyc_clean)
    
    # Get Road Network & OSMNX Logic
    try:
        nyc_graph = ox.graph_from_place("New York City, New York", network_type='drive', simplify=True)
        road_lines = ox.graph_to_gdfs(nyc_graph, nodes=False, edges=True).to_crs("EPSG:2263")
        road_lines['osm_street'] = road_lines['name'].apply(lambda x: x[0] if isinstance(x, list) else x)
        road_lines['osm_street'] = road_lines['osm_street'].apply(robust_nyc_clean)
        
        snapped = gpd.sjoin_nearest(road_lines, sensor_gdf, max_distance=500)
        snapped = snapped[snapped['osm_street'] == snapped['street_clean']]
        snapped['geometry'] = snapped['geometry'].simplify(tolerance=20)
        snapped_roads = snapped.to_crs("EPSG:4326")
    except Exception as e:
        st.error(f"Error processing map geometries: {e}")
        conn.close()
        return None, None

    # Train Model
    X = traffic_df[['segmentId', 'hour', 'dayOfWeek', 'isWeekend']]
    y = traffic_df['totalVolume']
    
    model = RandomForestRegressor(n_estimators=50, max_depth=15, n_jobs=-1, random_state=42)
    model.fit(X, y)
    
    conn.close()
    return model, snapped_roads

# Initialize Data
with st.spinner("Training model and loading map... This may take a minute."):
    model, snappedRoads = load_and_train_model()

if model is not None:
    # Sidebar UI
    st.sidebar.title("Map Controls")
    day_mapping = {
        'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 
        'Friday': 4, 'Saturday': 5, 'Sunday': 6
    }
    
    selected_day_name = st.sidebar.selectbox("Day of Week", list(day_mapping.keys()), index=0)
    selected_hour = st.sidebar.slider("Hour of Day", 0, 23, 12)
    
    # Prediction Logic
    day_int = day_mapping[selected_day_name]
    
    display_gdf = snappedRoads[['segmentId', 'street', 'geometry']].copy()
    display_gdf['hour'] = selected_hour
    display_gdf['dayOfWeek'] = day_int
    display_gdf['isWeekend'] = 1 if day_int >= 5 else 0
    
    # Run Prediction
    display_gdf['predictedVolume'] = model.predict(
        display_gdf[['segmentId', 'hour', 'dayOfWeek', 'isWeekend']]
    )

    st.title(f"NYC Traffic Volume Predictor")
    
    # Create three columns for the metrics
    col1, col2 = st.columns(2)
    
    with col1:
        unique_streets = display_gdf['street'].nunique()
        st.metric("Unique Streets", f"{unique_streets:,}")
        
    with col2:
        total_predicted_vol = int(display_gdf['predictedVolume'].sum())
        st.metric("Total Predicted Volume", f"{total_predicted_vol:,}")
        
    st.markdown("---")

    def get_borough(segment_id):
        # Mapping based on standard NYC DOT segment prefixes
        first_digit = str(segment_id)[0]
        mapping = {
            '1': 'Manhattan',
            '2': 'Bronx',
            '3': 'Brooklyn',
            '4': 'Queens',
            '5': 'Staten Island'
    }
        return mapping.get(first_digit, 'Other')

    # Apply mapping
    display_gdf['Borough'] = display_gdf['segmentId'].apply(get_borough)

    st.markdown("### Average Traffic Volume by Borough")

    # Prepare Data
    borough_avg = display_gdf.groupby('Borough')['predictedVolume'].mean().sort_values(ascending=False).reset_index()

    # Create Matplotlib Figure
    fig, ax = plt.subplots(figsize=(10, 4))
    sns.barplot(
        data=borough_avg, 
        x='Borough', 
        y='predictedVolume', 
        palette='viridis', 
        ax=ax
    )

    # Formatting
    ax.set_ylabel("Avg Predicted Volume Per Street (Cars/Hour)")
    ax.set_xlabel("")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Display in Streamlit
    st.pyplot(fig)

    st.markdown("---")

    # 24 Hour Trend Logic
    st.markdown("### 24 Hour Traffic Trend")

    # Create a range of all 24 hours
    all_hours = pd.DataFrame({'hour': range(24)})
    all_hours['dayOfWeek'] = day_int
    all_hours['isWeekend'] = 1 if day_int >= 5 else 0

    # Using the average segmentId to get a city wide representative prediction
    sample_segments = display_gdf['segmentId'].unique()[:50]
    trend_data = []

    for h in range(24):
        temp_df = pd.DataFrame({
            'segmentId': sample_segments,
            'hour': h,
            'dayOfWeek': day_int,
            'isWeekend': 1 if day_int >= 5 else 0
        })
        preds = model.predict(temp_df)
        trend_data.append({'hour': h, 'avg_vol': preds.mean()})

    trend_df = pd.DataFrame(trend_data)

    # Plotting the Hourly Histogram
    fig2, ax2 = plt.subplots(figsize=(12, 4))

    # Using a bar plot to act as a histogram of hourly averages
    sns.barplot(data=trend_df, x='hour', y='avg_vol', palette='coolwarm', ax=ax2)

    # Highlight the currently selected hour from the slider
    ax2.patches[selected_hour].set_edgecolor('black')
    ax2.patches[selected_hour].set_linewidth(2)
    ax2.patches[selected_hour].set_alpha(1.0)

    # Labels
    ax2.set_title(f"Average City-Wide Trend for {selected_day_name}")
    ax2.set_ylabel("Avg Volume (Cars/Hour)")
    ax2.set_xlabel("Hour of Day (0-23)")
    sns.despine()

    st.pyplot(fig2)

    st.markdown("---")

    # Day of Week Comparison Section
    st.markdown("### Average Traffic Volume by Day of Week")

    # Prepare the data for all 7 days
    days_list = list(day_mapping.keys())
    day_trend_data = []

    sample_segments_day = display_gdf['segmentId'].unique()[:50]

    for day_name in days_list:
	    d_int = day_mapping[day_name]
	    is_wknd = 1 if d_int >= 5 else 0
	
	    # Create temporary dataframe for prediction across each day
	    temp_day_df = pd.DataFrame({
		    'segmentId': sample_segments_day,
		    'hour': selected_hour,
		    'dayOfWeek': d_int,
		    'isWeekend': is_wknd
	    })
	
	    day_preds = model.predict(temp_day_df)
	    day_trend_data.append({'Day': day_name, 'AvgVolume': day_preds.mean()})

    day_trend_df = pd.DataFrame(day_trend_data)

    # Setup the Plot
    fig3, ax3 = plt.subplots(figsize=(10, 4))

    # Index of the day selected in the sidebar dropdown
    selected_day_index = days_list.index(selected_day_name)

    # Blue for Weekdays, Orange for Weekends
    base_colors = ['#3498db' if i < 5 else '#e67e22' for i in range(7)]

    # Create the bar plot
    sns.barplot(
	    data=day_trend_df, 
	    x='Day', 
	    y='AvgVolume', 
	    palette=base_colors, 
	    ax=ax3
    )

    # Apply the "Highlight" effect to the selected day
    for i, patch in enumerate(ax3.patches):
	    if i == selected_day_index:
		    # Highlighting the selected bar with a thick border
		    patch.set_edgecolor('black')
		    patch.set_linewidth(3)
		    patch.set_alpha(1.0)
	    else:
	    	# Fading non-selected bars for visual focus
	    	patch.set_alpha(0.5)

    # Final Formatting
    ax3.set_title(f"City-Wide Average Volume at {selected_hour}:00")
    ax3.set_ylabel("Avg Predicted Volume")
    ax3.set_xlabel("")
    plt.xticks(rotation=45)
    sns.despine() # Removes the top and right chart borders

    # Render the plot in Streamlit
    st.pyplot(fig3)

    # Map Rendering
    st.title(f"Predicted Traffic: {selected_day_name} at {selected_hour}:00")
    
    # Base Map
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=12, tiles='cartodbpositron')
    
    # Color Scale
    vmin = display_gdf['predictedVolume'].min()
    vmax = display_gdf['predictedVolume'].max()
    if vmin == vmax: vmax += 1
        
    color_scale = cm.LinearColormap(
        colors=['green', 'yellow', 'red'],
        vmin=vmin,
        vmax=vmax
    )
    
    # Styling lines
    def style_function(feature):
        return {
            'color': color_scale(feature['properties']['predictedVolume']),
            'weight': 4,
            'opacity': 0.7
        }

    folium.GeoJson(
        display_gdf,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=['street', 'predictedVolume'],
            aliases=['Street:', 'Predicted Vol:'],
            localize=True
        )
    ).add_to(m)
    
    color_scale.add_to(m)

    # Render in Streamlit
    # key="traffic_map" and returned_objects=[] prevents the refresh loop
    st_folium(
        m, 
        width=1400, 
        height=800, 
        key="traffic_map", 
        returned_objects=[]
    )
else:
    st.error("Failed to initialize the application. Please check your data files.")