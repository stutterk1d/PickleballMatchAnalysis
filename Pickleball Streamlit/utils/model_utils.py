import joblib
import streamlit as st
import shap
import matplotlib.pyplot as plt

@st.cache_resource
def load_ml_assets(model_path, scaler_path):
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    return model, scaler

def generate_shap_plot(model, scaled_input, input_df):
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(scaled_input)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    shap.summary_plot(shap_values, input_df, plot_type="bar", show=False)
    
    plt.title("SHAP Feature Importance")
    plt.tight_layout()
    
    st.pyplot(fig)
    plt.clf()