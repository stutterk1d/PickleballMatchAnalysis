import pandas as pd
import streamlit as st

@st.cache_data
def load_dataset(filepath):
    return pd.read_csv(filepath)