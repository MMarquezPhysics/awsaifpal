# Deploy AWS AIF Pal on Streamlit Community Cloud

The deployable app is in this `streamlitpal` folder. It includes the 512-question bank and requires no AWS account or API keys.

## Run it locally

From this folder, install Python dependencies and start the app:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit. Use Python 3.11 or newer.

## Deploy

1. Put the project in a GitHub repository. Keep `streamlitpal/app.py`, `streamlitpal/core.py`, `streamlitpal/style.css`, `streamlitpal/data/bank.json`, `streamlitpal/requirements.txt`, and `streamlitpal/.streamlit/config.toml` together.
2. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and choose **Create app**.
3. Select the repository and branch. Set the entrypoint file path to **`streamlitpal/app.py`**.
4. Choose a URL and select **Deploy**. Community Cloud installs `streamlitpal/requirements.txt` automatically.

If you upload only the `streamlitpal` folder as its own repository, set the entrypoint to **`app.py`** instead.

## How saved progress works

Attempts and the current session are saved in the visitor's browser storage. They survive page refreshes and Streamlit server restarts. They belong to that browser and site URL; they are not shared between devices or users. Clearing site data removes them. The **Download history JSON** button provides a personal backup of completed attempts. Browser storage must be enabled.

Streamlit Community Cloud's server filesystem is not used to store user data. The timer checks the original end time whenever the page is active or reloaded, so an expired session is submitted even after a browser reload.
