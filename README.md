# Pickleball Match Analysis

This repository holds a data science project for predicting pickleball match outcomes. You can find the code to scrape, clean, analyze, and model pickleball data here. I built a machine learning pipeline using XGBoost and K-Means clustering to classify different players. You can also run a Streamlit application to interact with the findings. 

## Project Structure

I divided the repository into specific folders and notebooks.

* **webscraping**: Contains scripts to scrape match data from pklmart.com and DUPR.com.
* **data**: Holds the raw and cleaned datasets. The final dataset includes over 900 matches.
* **Pickleball_Matches_Data_Cleaning.ipynb**: A notebook that cleans the raw scraped data.
* **Pickleball_Matches_Exploratory_Data_Analysis.ipynb**: A notebook for exploratory data analysis.
* **Pickleball_Match_Model_Evaluation.ipynb**: A notebook evaluating the machine learning models.
* **Pickleball_Streamlit**: Contains the code for the interactive Streamlit application.
* Unfortunately I was not able to scrape the DUPR scores so I had to obtain the DUPR scores of players by hand.

## Technologies Used

You will mainly use these tools for this project:

1. Python
2. Jupyter Notebook
3. Pandas and NumPy
4. XGBoost
5. Scikit-learn
6. Streamlit

## How to Run the Code

Follow these steps to run the project on your machine. 

1. Clone the repository to your local system.
2. Install the required Python packages.
3. Run the scripts in the `webscraping` folder to gather data, or use the files in the `data` folder.
4. Execute the Jupyter Notebooks in order: cleaning, exploratory data analysis, and model evaluation.
5. Open your Windows 11 terminal, change to the `Pickleball_Streamlit` directory, and launch the Streamlit app.

## Data Details

I collected data from two primary sources.

| Source | Purpose |
| :--- | :--- |
| pklmart.com | Match statistics |
| DUPR.com | Player ratings |

The web scraping process gives you a dataset of over 900 matches. The cleaning notebook handles missing values and formats the features for machine learning.

## Future Work

The current pipeline is only explores a fraction of what is possible. You can expand this project by doing things like:

* Testing other machine learning models like LightGBM or random forests.
* Automating the scraping process to run weekly.
* Creating a public API for the predictions.
