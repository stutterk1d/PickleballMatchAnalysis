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
MODEL_PATH = os.path.join(BASE_DIR, "models", "xgb_model.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "models", "scaler.pkl")

match_data = load_dataset(DATA_PATH)
xgb_classifier, feature_scaler = load_ml_assets(MODEL_PATH, SCALER_PATH)

st.sidebar.title("Menu")
app_mode = st.sidebar.radio(
    "Select a Module:",
    ['Data Explorer', 'Model Prediction', 'Match Simulation']
)

if app_mode == 'Data Explorer':
    st.header("Data Explorer")
    st.dataframe(match_data.head(100), use_container_width=True)

    if 'PCA1' in match_data.columns and 'PCA2' in match_data.columns and 'Playstyle' in match_data.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.scatterplot(data=match_data, x='PCA1', y='PCA2', hue='Playstyle', palette='viridis', ax=ax)
        ax.set_title("PCA Playstyle Clustering")
        st.pyplot(fig)
        plt.clf()

elif app_mode == 'Model Prediction':
    st.header("Model Prediction")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Team A")
        a_dupr = st.number_input("Average DUPR", value=5.5, key="a_dupr")
        a_drive = st.slider("Drive Percentage", 0.0, 1.0, 0.5, key="a_drive")
        a_cons = st.slider("Consistency", 0.0, 1.0, 0.8, key="a_cons")
        a_net = st.slider("Net Efficiency", -1.0, 1.0, 0.2, key="a_net")
        a_dupr_syn = st.number_input("DUPR Synergy", value=25.0, key="a_dupr_syn")

    with col2:
        st.subheader("Team B")
        b_dupr = st.number_input("Average DUPR", value=5.5, key="b_dupr")
        b_drive = st.slider("Drive Percentage", 0.0, 1.0, 0.5, key="b_drive")
        b_cons = st.slider("Consistency", 0.0, 1.0, 0.8, key="b_cons")
        b_net = st.slider("Net Efficiency", -1.0, 1.0, 0.2, key="b_net")
        b_d_n_syn = st.number_input("Driver Net Synergy", value=0.1, key="b_d_n_syn")
        b_dupr_syn = st.number_input("DUPR Synergy", value=25.0, key="b_dupr_syn")

    if st.button("Calculate Match Outcome"):
        features = [
            a_dupr - b_dupr,
            a_cons - b_cons,
            a_net - b_net,
            a_drive - b_drive,
            b_d_n_syn,
            a_dupr_syn,
            b_dupr_syn
        ]
        cols = ['DUPR_Diff', 'Consistency_Diff', 'Net_Efficiency_Diff', 'Drive_Diff', 'TeamB_Driver_Net_Synergy', 'TeamA_DUPR_Synergy', 'TeamB_DUPR_Synergy']
        input_df = pd.DataFrame([features], columns=cols)

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