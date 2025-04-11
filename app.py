import streamlit as st
import pandas as pd
import time
import os
import random
from datetime import datetime, time as dt_time
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import threading

# Custom CSS for better styling
st.markdown("""
    <style>
        .main {
            background-color: #f8f9fa;
        }
        .stTextInput input, .stTextArea textarea {
            border-radius: 8px;
            border: 1px solid #ced4da;
        }
        .stButton button {
            background-color: #4CAF50;
            color: white;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            border: none;
            font-weight: 500;
            width: 100%;
        }
        .stButton button:hover {
            background-color: #45a049;
        }
        .stNumberInput input {
            border-radius: 8px;
        }
        .stFileUploader {
            border-radius: 8px;
        }
        .stAlert {
            border-radius: 8px;
        }
        .progress-bar {
            height: 10px;
            background-color: #e9ecef;
            border-radius: 5px;
            margin: 10px 0;
        }
        .progress {
            height: 100%;
            background-color: #4CAF50;
            border-radius: 5px;
            transition: width 0.3s;
        }
        .status-box {
            background-color: #141414;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .schedule-item {
            background-color: #f1f1f1;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'sent_profiles' not in st.session_state:
    st.session_state.sent_profiles = set()
if 'messages_sent' not in st.session_state:
    st.session_state.messages_sent = 0
if 'scheduled_tasks' not in st.session_state:
    st.session_state.scheduled_tasks = []
if 'running' not in st.session_state:
    st.session_state.running = False
if 'download_key' not in st.session_state:
    st.session_state.download_key = 0

# Streamlit UI with improved layout
st.title("📱 Instagram Message Sender")
st.markdown("Send personalized messages to Instagram profiles from an Excel file")

# Create tabs for better organization
tab1, tab2, tab3 = st.tabs(["🔑 Configuration", "⏰ Schedule", "📊 Results"])

with tab1:
    # Form container for better organization
    with st.form("config_form"):
        st.subheader("Account Information")
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Instagram Username", placeholder="your_username")
        with col2:
            password = st.text_input("Instagram Password", type="password", placeholder="••••••••")
        
        st.subheader("Message Content")
        message_text = st.text_area("Message to Send", height=150, 
                                   placeholder="Hi there! I wanted to reach out about...")
        
        st.subheader("Sending Settings")
        col1, col2, col3 = st.columns(3)
        with col1:
            max_messages = st.number_input("Maximum Messages", min_value=1, value=48, 
                                         help="Maximum number of messages to send")
        with col2:
            time_interval = st.number_input("Batch Interval (sec)", min_value=20, value=600,
                                          help="Time between batches of messages")
        with col3:
            cooldown_min = st.number_input("Min Cooldown (min)", min_value=1, value=5)
        
        col1, col2 = st.columns(2)
        with col1:
            cooldown_max = st.number_input("Max Cooldown (min)", min_value=cooldown_min, value=5)
        with col2:
            uploaded_file = st.file_uploader("Upload Excel File", type=['xlsx'], 
                                           help="Excel file must contain a 'URL' column")
        
        submitted = st.form_submit_button("🚀 Start Sending Messages")

with tab2:
    st.subheader("Schedule Daily Runs")
    
    with st.form("schedule_form"):
        col1, col2 = st.columns(2)
        with col1:
            schedule_time = st.time_input("Run at this time daily", dt_time(9, 0))
        with col2:
            st.write("")  # Spacer
            st.write("")  # Spacer
            add_schedule = st.form_submit_button("➕ Add Schedule")
    
    if add_schedule:
        if uploaded_file is None:
            st.error("Please upload an Excel file first in the Configuration tab")
        elif not username or not password:
            st.error("Please enter your Instagram credentials first")
        else:
            # Store schedule in session state
            st.session_state.scheduled_tasks.append({
                'time': schedule_time.strftime("%H:%M"),
                'file': uploaded_file,
                'username': username,
                'password': password,
                'message': message_text,
                'max_messages': max_messages,
                'time_interval': time_interval,
                'cooldown_min': cooldown_min,
                'cooldown_max': cooldown_max
            })
            st.success(f"Scheduled to run daily at {schedule_time.strftime('%H:%M')}")
    
    # Display current schedules
    st.subheader("Active Schedules")
    if not st.session_state.scheduled_tasks:
        st.info("No schedules set up yet")
    else:
        for i, task in enumerate(st.session_state.scheduled_tasks):
            with st.expander(f"Schedule {i+1} - {task['time']}"):
                st.write(f"📅 Runs daily at {task['time']}")
                st.write(f"📊 Max messages: {task['max_messages']}")
                st.write(f"💬 Message: {task['message'][:50]}...")
                if st.button(f"Remove Schedule {i+1}", key=f"remove_{i}"):
                    st.session_state.scheduled_tasks.pop(i)
                    st.rerun()



# Status container (visible when running)
status_container = st.empty()

def load_profiles(file):
    try:
        df = pd.read_excel(file)
        if 'URL' not in df.columns:
            st.error("Excel file must contain a 'URL' column")
            return None
        profiles = df["URL"].str.strip().tolist()
        return profiles
    except Exception as e:
        st.error(f"Error loading profiles: {e}")
        return None

def load_sent_profiles():
    """Load already sent profiles from results file"""
    sent_profiles = set()
    if os.path.exists("Profile_links_updated.csv"):
        try:
            df = pd.read_csv("Profile_links_updated.csv")
            sent_profiles = set(df[df['Status'] == 'Success']['Profile URL'].tolist())
        except:
            pass
    return sent_profiles

def update_results(file_path):
    try:
        if os.path.exists(file_path):
            results_df = pd.read_csv(file_path)
            with tab3:
                st.dataframe(results_df, height=400)
                # Increment the download key each time to ensure uniqueness
                st.session_state.download_key += 1
                st.download_button(
                    label="📥 Download Results",
                    data=results_df.to_csv(index=False).encode('utf-8'),
                    file_name='instagram_message_results.csv',
                    mime='text/csv',
                    key=f"download_{st.session_state.download_key}"  # Unique key
                )
    except Exception as e:
        st.error(f"Error reading results file: {e}")
with tab3:
    results_placeholder = st.empty()
    if os.path.exists("Profile_links_updated.csv"):
        update_results("Profile_links_updated.csv")
    else:
        st.info("No results to display yet. Run the message sender to see results here.")
def show_status(message, progress=None):
    with status_container:
        with st.expander("🔍 Current Status", expanded=True):
            if progress is not None:
                st.markdown(f"""
                    <div class="progress-bar">
                        <div class="progress" style="width: {progress}%"></div>
                    </div>
                """, unsafe_allow_html=True)
            st.markdown(f"""
                <div class="status-box">
                    <p>{message}</p>
                </div>
            """, unsafe_allow_html=True)

def run_script(profiles, config):
    # Configure Chrome options
    chrome_options = Options()
    prefs = {
        "profile.default_content_setting_values.notifications": 2,  # Block notifications
    }
    chrome_options.add_experimental_option("prefs", prefs)
    # Headless mode (no GUI)
    chrome_options.add_argument("--headless=new")  # New headless mode in Chrome 109+
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security
    chrome_options.add_argument("--disable-dev-shm-usage")  # Prevent crashes in Docker/Linux
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception as e:
        show_status(f"Error initializing WebDriver: {e}")
        return False

    def login():
        try:
            show_status("Logging in to Instagram...")
            driver.get("https://www.instagram.com/accounts/login/")
            
            try:
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow')]"))
                ).click()
            except:
                pass
            
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, 'username'))
            )
            for char in config['username']:
                username_field.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, 'password'))
            )
            for char in config['password']:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
            ).click()
            
            time.sleep(5)
            try:
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
                ).click()
            except:
                pass
            
            show_status("Login successful ✅")
            return True
            
        except Exception as e:
            show_status(f"Login failed ❌: {e}")
            return False

    def send_message(profile_url, message_text):
        # Skip if already sent to this profile
        if profile_url in st.session_state.sent_profiles:
            show_status(f"Skipping already sent profile: {profile_url}")
            return False
            
        try:
            driver.get(profile_url)
            time.sleep(random.uniform(2, 4))
            
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, 
                "//div[@class='x9f619 xjbqb8w x78zum5 x168nmei x13lgxp2 x5pf9jr xo71vjh x1n2onr6 x6ikm8r x10wlt62 x1iyjqo2 x2lwn1j xeuugli xdt5ytf xqjyukv x1qjc9v5 x1oa3qoh x1nhvcw1']"))
            ).click()
            paragraphs = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//p[@class='xat24cr xdj266r']")))
            paragraphs.send_keys(message_text)
            paragraphs.send_keys(Keys.ENTER)

        except TimeoutException:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, 
                    "//div[@class='x1q0g3np x2lah0s']"))
                ).click()
            except TimeoutException:
                show_status(f"Neither button found for profile: {profile_url}")
                with open("Profile_links_updated.csv", 'a', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow([profile_url, "Failed (Button not found)", message_text,datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                return False
        
        try:
            WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, 
                "//button[contains(., 'Send message')]"))
            ).click()
            paragraphs = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//p[@class='xat24cr xdj266r']")))
            paragraphs.send_keys(message_text)
            paragraphs.send_keys(Keys.ENTER)
            # Mark as sent
            st.session_state.sent_profiles.add(profile_url)
            st.session_state.messages_sent += 1
            
            # Record success
            with open("Profile_links_updated.csv", 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([profile_url, "Success", message_text,datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            
            progress = (st.session_state.messages_sent / config['max_messages']) * 100
            show_status(f"✅ Message sent to {profile_url} (Total: {st.session_state.messages_sent}/{config['max_messages']})", progress)
            
            time.sleep(random.uniform(5, 10))
            return True
            
        except TimeoutException:
            show_status(f"Send message button not found for {profile_url}")
            with open("Profile_links_updated.csv", 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([profile_url, "Failed (Send button)", message_text,datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            return False
    
    # Reset counters at start
    st.session_state.messages_sent = 0
    start_time = time.time()
    
    # Load previously sent profiles from file
    st.session_state.sent_profiles = load_sent_profiles()
    
    if not login():
        show_status("Cannot continue without login ❌")
        driver.quit()
        return
    
    # Create results file if doesn't exist
    if not os.path.exists("Profile_links_updated.csv"):
        with open("Profile_links_updated.csv", 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Profile URL', 'Status',"message", 'Timestamp'])
    
    # Process profiles
    for idx, profile in enumerate(profiles, 1):
        # Check message limit first
        if st.session_state.messages_sent >= config['max_messages']:
            show_status(f"Message limit reached ({config['max_messages']} messages sent) ✅")
            break
            
        # Check time interval
        if time.time() - start_time > config['time_interval']:
            cooldown = random.uniform(config['cooldown_min']*60, config['cooldown_max']*60)
            show_status(f"⏳ Cooling down for {cooldown/60:.1f} minutes...")
            time.sleep(cooldown)
            start_time = time.time()
            
        send_message(profile, config['message'])
        
        # Random delay between attempts
        delay = random.uniform(10, 30)
        show_status(f"⏳ Waiting {delay:.1f} seconds before next message...")
        time.sleep(delay)
        
        update_results("Profile_links_updated.csv")
    
    show_status("Script completed successfully! ✅")
    driver.quit()

def run_scheduled_task(task):
    show_status(f"⏰ Running scheduled task at {task['time']}")
    profiles = load_profiles(task['file'])
    if profiles:
        run_script(profiles, task)

def schedule_checker():
    while st.session_state.running:
        now = datetime.now().strftime("%H:%M")
        for task in st.session_state.scheduled_tasks:
            if task['time'] == now:
                run_scheduled_task(task)
                # Wait a minute to prevent running multiple times
                time.sleep(60)
        time.sleep(30)  # Check every 30 seconds

# Start the scheduler thread when there are scheduled tasks
if st.session_state.scheduled_tasks and not st.session_state.running:
    st.session_state.running = True
    threading.Thread(target=schedule_checker, daemon=True).start()

# Run when form is submitted
if submitted and uploaded_file:
    profiles = load_profiles(uploaded_file)
    if profiles:
        config = {
            'username': username,
            'password': password,
            'message': message_text,
            'max_messages': max_messages,
            'time_interval': time_interval,
            'cooldown_min': cooldown_min,
            'cooldown_max': cooldown_max
        }
        run_script(profiles, config)