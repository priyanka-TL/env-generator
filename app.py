import os
import re
import requests
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from io import BytesIO
import openai
from math import ceil
from dotenv import load_dotenv
import sqlite3

from config import SERVICE_URLS, ENV_VARIABLES_URLS, REPLACEABLE_ENV_VARIABLES
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')  # Use environment variable for secret key

# OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

app.config['MAX_QUESTIONS'] = int(os.getenv('MAX_QUESTIONS', 10))  # Configure max questions to ask
app.config['SESSION_TYPE'] = 'filesystem' 

DATABASE_FILE = os.getenv('DATABASE_FILE', 'env_gen.db') 

def init_db():
    """Initialize the SQLite database and create the questions table."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Create questions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            variable_name TEXT NOT NULL,
            question TEXT NOT NULL,
            is_mandatory BOOLEAN NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

def fetch_questions_from_db(service_name):
    """Fetch questions for a specific service from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT variable_name, question, is_mandatory
        FROM questions
        WHERE service_name = ?
    """, (service_name,))
    questions = cursor.fetchall()

    conn.close()

    # Format questions as a dictionary
    return {
        "mandatory": [
            {"name": q[0], "question": q[1]}
            for q in questions if q[2]  # is_mandatory is True
        ],
        "non_mandatory": [
            {"name": q[0], "question": q[1]}
            for q in questions if not q[2]  # is_mandatory is False
        ]
    }

def check_and_fetch_missing_questions(service_name, env_variables, parsed_variables):
    """Check if all keys exist in the database. If not, call AI and store missing questions."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Fetch existing keys for the service
    cursor.execute("""
        SELECT variable_name
        FROM questions
        WHERE service_name = ?
    """, (service_name,))
    existing_keys = {row[0] for row in cursor.fetchall()}

    # Find missing keys
    all_keys = parsed_variables.get("all_keys", [])
    missing_keys = set(all_keys) - existing_keys

    if missing_keys:
        # Generate questions for missing keys using AI
        missing_questions = generate_questions({
            key: env_variables.get(key, "Not defined")
            for key in missing_keys
        })

        # Store missing questions in the database
        for key, question in zip(missing_keys, missing_questions):
            is_mandatory = key in parsed_variables.get("mandatory", [])

            cursor.execute("""
                INSERT INTO questions (service_name, variable_name, question, is_mandatory)
                VALUES (?, ?, ?, ?)
            """, (service_name, key, question, is_mandatory))

        conn.commit()

    conn.close()


def fetch_file_content(url):
    """Fetch the content of a .env file from a GitHub URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return str(e)

def parse_env_file(env_content):
    """
    Parse the .env content into a dictionary.
    
    Args:
        env_content (str): The content of the .env file as a string.
        
    Returns:
        dict: A dictionary of environment variables.
    """
    env_variables = {}
    for line in env_content.splitlines():
        # Remove leading and trailing whitespace
        line = line.strip()

        # Skip empty lines and full-line comments
        if not line or line.startswith("#"):
            continue

        # Handle inline comments (anything after a space + #)
        line = re.split(r'\s+#', line, maxsplit=1)[0].strip()

        # Match key=value lines
        match = re.match(r'^([\w\-.]+)\s*=\s*(.+)$', line)
        if match:
            key, value = match.groups()

            # Handle quoted values (strip surrounding quotes)
            if value.startswith(("'", '"')) and value.endswith(("'", '"')):
                value = value[1:-1]

            # Remove any additional surrounding spaces
            value = value.strip()

            # Add to dictionary
            env_variables[key] = value
        else:
            # Log invalid lines for debugging
            print(f"Skipping invalid line: {line}")

    return env_variables

def generate_questions(env_variables):
    """
    Use OpenAI API to generate meaningful questions for environment variables using their keys and values.

    Args:
        env_variables (dict): A dictionary of environment variable key-value pairs.

    Returns:
        list: A list of generated questions.
    """
    # Create a prompt using key-value pairs
    prompt = (
        "For the following environment variables, generate one clear and user-friendly question per key-value pair. "
        "The questions should be easy to understand and should provide context about what the variable is used for. "
        "Do not include any extra text or introduction, only the questions:\n\n"
        "- For each key-value pair, generate a question that explains what the variable does and asks for its value.\n"
        "- Use simple and concise language.\n"
        "- Avoid technical jargon unless necessary.\n"
        "- If the key name is descriptive, use it to form the question.\n"
        "- If the key name is not descriptive, infer its purpose based on common naming conventions.\n\n"
        "Example:\n"
        "- For `APPLICATION_PORT=3000`, the question could be: 'What port should the application run on?'\n"
        "- For `DATABASE_URL=postgres://user:password@localhost:5432/mydb`, the question could be: 'What is the connection URL for the database?'\n\n"
        "Now, generate questions for the following key-value pairs:\n"
    )
    for key, value in env_variables.items():
        prompt += f"- {key}={value}\n"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        # Parse the response into a list of questions
        questions = response['choices'][0]['message']['content'].strip().split("\n")
        return questions
    except Exception as e:
        print(f"Error: {e}")
        # Fallback questions in case of an API error
        return [f"What is the value of {key}?" for key in env_variables.keys()]

@app.route('/')
def home():
    return render_template('home.html', services=SERVICE_URLS.keys())

def parse_env_variables_js(content):
    """
    Parses the JavaScript environment variable definitions into mandatory and non-mandatory categories.

    Args:
        content (str): The JavaScript content containing environment variable definitions.

    Returns:
        dict: A dictionary with 'mandatory' and 'non_mandatory' lists of variables.
    """
    pattern = r'([A-Z_]+):\s*{[^}]*optional:\s*(true|false)[^}]*}'
    # Find all matches
    matches = re.findall(pattern, content)

    mandatory = []
    non_mandatory = []
    all_keys = []

    if matches:
        for var_name, var_optional in matches:
            # Categorize based on the 'optional' field
            if var_optional == 'true':
                non_mandatory.append(var_name)
            else:
                mandatory.append(var_name)
            all_keys.append(var_name)
        
        # Extract default values
        default_pattern = r'([A-Z_]+):\s*{[^}]*default:\s*([^,}]+)[^}]*}'
        default_matches = re.findall(default_pattern, content)

        default_values = {}
        for var_name, default_value in default_matches:
            default_value = default_value.strip().strip('"').strip("'")
            default_values[var_name] = default_value

        return {"mandatory": mandatory, "non_mandatory": non_mandatory, "all_keys": all_keys, "default_values": default_values}
    else:
        raise ValueError("Could not parse the JavaScript environment variables. Ensure the object is defined correctly.")

@app.route('/fetch', methods=['POST'])
def fetch():
    service_name = request.form.get('service')

    # Validate service selection
    if not service_name or service_name not in SERVICE_URLS:
        return render_template(
            'home.html',
            services=SERVICE_URLS.keys(),
            error_message="Invalid service selected. Please try again."
        )
    
    # Clear session data
    session.pop('mandatory', None)
    session.pop('non_mandatory', None)
    session.pop('env_sample', None)
    session.pop('user_answers', None)

    # Fetch env files
    env_url = SERVICE_URLS[service_name]
    variables_url = ENV_VARIABLES_URLS[service_name]

    env_content = fetch_file_content(env_url)
    variables_content = fetch_file_content(variables_url)

    if not env_content or "Error" in env_content:
        return render_template('home.html', services=SERVICE_URLS.keys(),
                               error_message=f"Error fetching .env file: {env_content}")
    
    # Parse .env and JavaScript variables
    env_variables = parse_env_file(env_content)  # This returns a key-value dictionary
    parsed_variables = parse_env_variables_js(variables_content)

    # Check for missing keys and fetch questions from AI if needed
    check_and_fetch_missing_questions(service_name, env_variables, parsed_variables)

    # Fetch questions from the database
    questions = fetch_questions_from_db(service_name)

    # Add default values from parsed_variables and .env sample values
    default_values = parsed_variables.get("default_values", {})
    for question in questions["mandatory"] + questions["non_mandatory"]:
        question_name = question["name"]
        # Use .env sample value if available, otherwise use default value
        question["value"] = env_variables.get(question_name, default_values.get(question_name, ""))

    # Initialize user_answers and env_sample with all keys from parsed_variables["all_keys"]
    user_answers = {}
    env_sample = {}

    for key in parsed_variables["all_keys"]:
        # Use .env sample value if available, otherwise use default value
        value = env_variables.get(key, default_values.get(key, ""))
        user_answers[key] = value
        env_sample[key] = value

    # Store data in session
    session['mandatory'] = questions["mandatory"]
    session['non_mandatory'] = questions["non_mandatory"]
    session['env_sample'] = env_sample  # Store all keys with their values
    session['user_answers'] = user_answers  # Store all keys with their values

    return redirect(url_for('questions'))

@app.route('/questions', methods=['GET', 'POST'])
def questions():
    mandatory_questions = session.get('mandatory', [])
    non_mandatory_questions = session.get('non_mandatory', [])
    user_answers = session.get('user_answers', {})
    env_sample = session.get('env_sample', {})

    current_tab = request.args.get('tab', 'mandatory')  # Default to 'mandatory'
    page_size = app.config.get('MAX_QUESTIONS', 10)

    if current_tab == 'mandatory':
        questions = mandatory_questions
        page_key = 'mandatory_page'
    else:
        questions = non_mandatory_questions
        page_key = 'non_mandatory_page'

    current_page = int(request.args.get(page_key, 1))
    total_pages = ceil(len(questions) / page_size)

    # Ensure current_page is within valid bounds
    current_page = max(1, min(current_page, total_pages))
    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    questions_to_display = questions[start_index:end_index]

    if request.method == 'POST':
        form_data = request.form.to_dict()

        # Update user_answers with submitted form data
        for question in mandatory_questions + non_mandatory_questions:
            question_name = question['name']
            user_answers[question_name] = form_data.get(question_name, user_answers.get(question_name, question.get("default_value", "")))

        # Save the updated answers back to the session
        session['user_answers'] = user_answers
        session.modified = True
        # Redirect to the generate route to download the .env file
        return redirect(url_for('generate'))

    return render_template(
        'questions.html',
        questions_to_display=questions_to_display,
        user_answers=user_answers,
        env_sample=env_sample,
        current_page=current_page,
        total_pages=total_pages,
        tab=current_tab  # Pass the current_tab to the template
    )

@app.route('/update_answer', methods=['POST'])
def update_answer():
    data = request.get_json()
    key = data.get('key')
    value = data.get('value')

    if not key:
        return jsonify({"error": "Key is required"}), 400

    # Update user_answers in the session
    user_answers = session.get('user_answers', {})
    user_answers[key] = value
    session['user_answers'] = user_answers
    session.modified = True

    return jsonify({"success": True, "key": key, "value": value})

@app.route('/generate', methods=['GET'])
def generate():
    user_answers = session.get('user_answers', {})
    env_sample = session.get('env_sample', {})

    # Track which variables have been updated
    updated_variables = []

    # Merge user answers with env_sample
    merged_env = {}
    for key in env_sample.keys():
        user_value = user_answers.get(key)
        sample_value = env_sample.get(key, "")

        # Use the user's value if it exists, otherwise fallback to the sample value
        merged_env[key] = user_value if user_value is not None else sample_value

        # Check if the variable is in the replaceable list and has been updated
        if REPLACEABLE_ENV_VARIABLES and key in REPLACEABLE_ENV_VARIABLES:
            # Fetch the value from os.getenv
            env_value = os.getenv(key)
            if env_value is not None:
                merged_env[key] = env_value
                updated_variables.append(key)

    # Generate .env content
    env_content = "\n".join([f"{key}={value}" for key, value in merged_env.items()])

    # Generate a report of updated variables
    update_report = "; ".join([f"{key} was updated to: {merged_env.get(key)}" for key in updated_variables])

    # Return the .env file and the update report
    return (env_content, 200, {
        'Content-Type': 'text/plain',
        'Content-Disposition': 'attachment; filename=".env"',
        'X-Updated-Variables': update_report  # Use a delimiter like "; " instead of newlines
    })

def validate_env_variables():
    """
    Validate that all required environment variables are set.
    If any variable is missing, raise an error and provide a table format.
    """
    required_env_vars = [
        {
            "name": "SECRET_KEY",
            "description": "Flask secret key for session encryption"
        },
        {
            "name": "OPENAI_API_KEY",
            "description": "API key for OpenAI services"
        },
        {
            "name": "CLOUD_STORAGE_PROVIDER",
            "description": "Cloud storage provider in azure, aws, gcloud, oci or s3"
        },
        {
            "name": "CLOUD_STORAGE_ACCOUNTNAME",
            "description": "Cloud storage identity [Azure Account Name, AWS Access Key, GCP Client Email, OCI S3 Access Key or S3 Access Key]"
        },
        {
            "name": "CLOUD_STORAGE_SECRET",
            "description": "Cloud storage secret"
        },
        {
            "name": "CLOUD_STORAGE_REGION",
            "description": "Cloud storage region for AWS and OCI only"
        },
        {
            "name": "CLOUD_ENDPOINT",
            "description": "Cloud storage endpoint for S3 and OCI only"
        },
        {
            "name": "CLOUD_STORAGE_BUCKETNAME",
            "description": "Cloud storage default bucket name"
        },
        {
            "name": "PUBLIC_ASSET_BUCKETNAME",
            "description": "Cloud storage public bucket name"
        },
        {
            "name": "CLOUD_STORAGE_BUCKET_TYPE",
            "description": "Cloud storage default bucket type"
        }
    ]

    # Extract missing variables
    missing_vars = [var for var in required_env_vars if not os.getenv(var["name"])]

    if missing_vars:
        # Create a table format for missing variables
        table_header = f"{'Variable Name':<30} | {'Description':<40}\n" + "-" * 73
        table_rows = "\n".join([
            f"{var['name']:<30} | {var['description']:<40}" 
            for var in missing_vars
        ])

        message = (
            "The following required environment variables are missing or not set:\n"
            "Please ensure that all required variables are defined in the environment or .env file.\n"
        )

        # Raise an error with only the table format
        raise EnvironmentError(f"\n{message}{table_header}\n{table_rows}")

# Call the validation function before starting the app
try:
    validate_env_variables()
except EnvironmentError as e:
    print(e)  # Cleanly print the error message (the table in this case)
    exit(1)  

if __name__ == '__main__':
    app.run(debug=True)