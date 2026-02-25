import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from utils.data_loader import load_dataset
from utils.model_utils import load_ml_assets, generate_shap_plot
from utils.markov_sim import simulate_match
import os

st.set_page_config(
    page_title="Pickleball Analytics",
    page_icon="🤾‍♀️🥒🏓",
    layout="wide"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_PATH = os.path.join(BASE_DIR, "data", "matches_complete7.0.csv")
PLAYER_DATA_PATH = os.path.join(BASE_DIR, "data", "player_playstyles_complete.csv")
MODEL_PATH = os.path.join(BASE_DIR, "models", "xgb_model.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "models", "scaler.pkl")

match_data = load_dataset(DATA_PATH)
player_data = load_dataset(PLAYER_DATA_PATH)
xgb_classifier, feature_scaler = load_ml_assets(MODEL_PATH, SCALER_PATH)

st.sidebar.title("Menu")
app_mode = st.sidebar.radio(
    "Select a Module:",
    ['Data Explorer', 'Model Prediction', 'Match Simulation']
)

if app_mode == 'Data Explorer':
    st.header("Data Explorer")
    st.dataframe(match_data.head(1000), use_container_width=True)

    if 'PCA1' in player_data.columns and 'PCA2' in player_data.columns and 'Playstyle_Cluster' in player_data.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.scatterplot(data=player_data, x='PCA1', y='PCA2', hue='Playstyle_Cluster', palette='viridis', ax=ax)
        ax.set_title("PCA Playstyle Clustering (Players)")
        st.pyplot(fig)
        plt.clf()

elif app_mode == 'Model Prediction':
    st.header("Model Prediction")
    col1, col2 = st.columns(2)
    
    # Map descriptive names to your model's cluster IDs
    style_map = {
        "Banger": "Cluster_0", 
        "Dinker": "Cluster_1", 
        "Hybrid": "Cluster_2"
    }
    display_options = list(style_map.keys())

    with col1:
        st.subheader("Team A")
        a_dupr = st.number_input("Average DUPR", value=5.5, key="a_dupr", help="The combined average player rating for the team.")
        a_p1_display = st.selectbox("Player 1 Playstyle", display_options, key="a_p1_style")
        a_p2_display = st.selectbox("Player 2 Playstyle", display_options, key="a_p2_style")
        a_drive = st.slider("Drive Percentage", 0.0, 1.0, 0.5, key="a_drive", help="Percentage of 3rd shots hit as fast drives instead of soft drops.")
        a_cons = st.slider("Consistency", 0.0, 1.0, 0.8, key="a_cons", help="The rate at which the team keeps the ball in play without committing unforced errors.")
        a_net = st.slider("Net Efficiency", -1.0, 1.0, 0.2, key="a_net", help="How well the team wins points when positioned at the non-volley zone line.")
        a_dupr_syn = st.number_input("DUPR Synergy", value=25.0, key="a_dupr_syn", help="A calculated score showing how well the two players' ratings complement each other.")

    with col2:
        st.subheader("Team B")
        b_dupr = st.number_input("Average DUPR", value=5.5, key="b_dupr")
        b_p1_display = st.selectbox("Player 1 Playstyle", display_options, key="b_p1_style")
        b_p2_display = st.selectbox("Player 2 Playstyle", display_options, key="b_p2_style")
        b_drive = st.slider("Drive Percentage", 0.0, 1.0, 0.5, key="b_drive")
        b_cons = st.slider("Consistency", 0.0, 1.0, 0.8, key="b_cons")
        b_net = st.slider("Net Efficiency", -1.0, 1.0, 0.2, key="b_net")
        b_d_n_syn = st.number_input("Driver Net Synergy", value=0.1, key="b_d_n_syn", help="Measures the effectiveness of pairing an aggressive driver with a strong net player.")
        b_dupr_syn = st.number_input("DUPR Synergy", value=25.0, key="b_dupr_syn")

    if st.button("Calculate Match Outcome"):
        base_cols = ['DUPR_Diff', 'Consistency_Diff', 'Net_Efficiency_Diff', 'Drive_Diff', 'TeamB_Driver_Net_Synergy', 'TeamA_DUPR_Synergy', 'TeamB_DUPR_Synergy']
        
        # Define the exact columns your model expects
        cluster_options = ['Cluster_0', 'Cluster_1', 'Cluster_2']
        players = ['TeamAPlayer1', 'TeamAPlayer2', 'TeamBPlayer1', 'TeamBPlayer2']
        playstyle_cols = [f"{p}_Playstyle_{c}" for p in players for c in cluster_options]
        
        all_cols = base_cols + playstyle_cols

        input_data = {
            'DUPR_Diff': a_dupr - b_dupr,
            'Consistency_Diff': a_cons - b_cons,
            'Net_Efficiency_Diff': a_net - b_net,
            'Drive_Diff': a_drive - b_drive,
            'TeamB_Driver_Net_Synergy': b_d_n_syn,
            'TeamA_DUPR_Synergy': a_dupr_syn,
            'TeamB_DUPR_Synergy': b_dupr_syn
        }

        # Set all playstyle columns to 0 initially
        for col in playstyle_cols:
            input_data[col] = 0

        # Find the correct cluster ID based on the user's text selection
        a_p1_model_val = style_map[a_p1_display]
        a_p2_model_val = style_map[a_p2_display]
        b_p1_model_val = style_map[b_p1_display]
        b_p2_model_val = style_map[b_p2_display]

        # Set the selected playstyles to 1
        input_data[f"TeamAPlayer1_Playstyle_{a_p1_model_val}"] = 1
        input_data[f"TeamAPlayer2_Playstyle_{a_p2_model_val}"] = 1
        input_data[f"TeamBPlayer1_Playstyle_{b_p1_model_val}"] = 1
        input_data[f"TeamBPlayer2_Playstyle_{b_p2_model_val}"] = 1

        input_df = pd.DataFrame([input_data], columns=all_cols)

        scaled_input = feature_scaler.transform(input_df)
        prob = xgb_classifier.predict_proba(scaled_input)[0][1]

        st.write(f"Team A Win Probability: {prob * 100:.1f}%")
        generate_shap_plot(xgb_classifier, scaled_input, input_df)

elif app_mode == 'Match Simulation':
    st.header("Match Simulation")
    p_win_a = st.slider("Team A Point Win Probability", 0.0, 1.0, 0.5)
    p_win_b = st.slider("Team B Point Win Probability", 0.0, 1.0, 0.5)

    if st.button("Run Simulation"):
        winner, score_a, score_b, rallies, history_a, history_b = simulate_match(p_win_a, p_win_b)
        st.write(f"Winner: {winner} ({score_a} - {score_b})")

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(history_a, label="Team A")
        ax.plot(history_b, label="Team B")
        ax.axhline(11, color='green', linestyle='--')
        ax.set_title("Match Score Progression")
        ax.set_xlabel("Rally Number")
        ax.set_ylabel("Total Points")
        ax.legend()
        
        st.pyplot(fig)
        plt.clf()