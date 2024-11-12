import streamlit as st
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import firebase_admin
from firebase_admin import credentials, firestore, storage
import time
import random
import string
import pandas as pd
import os
import json
# from dotenv import load_dotenv

# load_dotenv()

firebase_secrets = json.loads(os.environ['firebase_credentials'])
storage_bucket = os.environ['storage_bucket']

# Firebase initialization
if not firebase_admin._apps:  # Check if the app has already been initialized
    cred = credentials.Certificate(firebase_secrets)
    firebase_admin.initialize_app(cred, {
        'storageBucket': storage_bucket
    })


# Access Firebase services
db = firestore.client()
bucket = storage.bucket()

# Prompt for username if not set
if "username" not in st.session_state:
    st.session_state.username = None

if st.session_state.username is None:
    # Create a form for entering the username
    with st.form("username_form"):
        username_input = st.text_input("Enter your username:", placeholder="Enter a unique username")
        submit_button = st.form_submit_button("Submit")

        # If the submit button is pressed and a username is entered
        if submit_button:
            if username_input.strip() == "":
                st.warning("Please enter a valid username.")
            else:
                st.session_state.username = username_input.strip()
                st.rerun()  # Refresh to load the app with the username set

# Proceed if the username is set
if st.session_state.username:
    # Display username in sidebar
    st.sidebar.title("User Info")
    st.sidebar.write(f"Username: {st.session_state.username}")

    # Main App Layout
    st.title("LyngualLabs Crowdsourcing App")
    st.write("Help us collect data for Yoruba-English code-switching! Record yourself reading the prompt below.")

    # Load prompts and assign a unique prompt to each user only if not already set
    if "current_prompt" not in st.session_state or st.session_state.current_prompt is None:
        prompts = pd.read_csv("prompts.csv")
        
        # Retrieve list of completed prompts for the user
        completed_prompts = [doc.get("text_prompt") for doc in db.collection("recordings").where("user_id", "==", st.session_state.username).stream()]
        available_prompts = prompts[~prompts["prompt"].isin(completed_prompts)]
        
        # Assign a unique prompt if available
        if not available_prompts.empty:
            st.session_state.current_prompt = available_prompts.sample(1).iloc[0]["prompt"]
        else:
            st.session_state.current_prompt = None  # No more prompts available

    # Display the prompt
    if st.session_state.current_prompt:
        current_prompt = st.session_state.current_prompt
        st.subheader("Prompt:")
        st.write(current_prompt)
    else:
        st.write("No more prompts available for you to record. Thank you for your contributions!")

    # Define recording settings
    fs = 44100  # Sample rate
    duration = 5  # Duration of recording in seconds

    # Stage 1: Recording Part
    if "audio_filename" not in st.session_state:
        st.session_state.audio_filename = None

    if st.button("Start Recording") and st.session_state.current_prompt:
        st.write("Recording... Please read the prompt.")
        audio_data = sd.rec(int(duration * fs), samplerate=fs, channels=2)
        sd.wait()  # Wait until recording is finished
        st.write("Recording complete!")

        # Create a unique filename using username, timestamp, and random characters
        timestamp = int(time.time())
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        st.session_state.audio_filename = f"{st.session_state.username}_{timestamp}_{random_str}.wav"

        # Save recording to a WAV file
        write(st.session_state.audio_filename, fs, audio_data)
        st.write(f"Audio saved locally as {st.session_state.audio_filename}.")
        
        # Provide playback option
        st.audio(st.session_state.audio_filename)

    # Stage 2: Upload/Discard Part (only show after recording)
    if st.session_state.audio_filename:
        st.write("Review your recording and choose an action:")

        # Feedback section
        rating = st.radio("Rate the quality of this recording:", ('Good', 'Average', 'Poor'), key="rating")
        comments = st.text_input("Comments (optional):", key="comments")

        # Display Upload and Discard buttons in columns
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Upload Recording"):
                try:
                    # Upload audio to Firebase Storage
                    blob = bucket.blob(f"audio/{st.session_state.audio_filename}")
                    blob.upload_from_filename(st.session_state.audio_filename)
                    st.write("Audio uploaded to Firebase.")

                    # Store metadata in Firestore
                    db.collection("recordings").add({
                        "user_id": st.session_state.username,
                        "text_prompt": current_prompt,
                        "audio_path": f"audio/{st.session_state.audio_filename}",
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "rating": rating,
                        "comments": comments
                    })
                    st.success("Your contribution has been submitted!")

                    # Initialize a single progress bar
                    progress_bar = st.progress(0)
                    for percent in range(100):
                        progress_bar.progress(percent + 1)
                        time.sleep(0.01)  # Simulate a delay of 1 second

                    # Clear session state for a new recording
                    st.session_state.current_prompt = None
                    st.session_state.audio_filename = None
                    st.rerun()

                except Exception as e:
                    st.error(f"An error occurred during upload: {e}")

        with col2:
            if st.button("Discard Recording"):
                # Discard action clears the saved audio and feedback fields
                st.session_state.audio_filename = None
                st.write("Recording discarded. Ready to start a new one.")
                # Reset the current prompt
                st.session_state.current_prompt = None
                st.rerun()
