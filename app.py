import os
import re
import requests
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_file
from io import BytesIO
import openai
from dotenv import load_dotenv

from config import SERVICE_URLS, ENV_VARIABLES_URLS
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')  # Use environment variable for secret key

# OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

app.config['MAX_QUESTIONS'] = int(os.getenv('MAX_QUESTIONS', 10))  # Configure max questions to ask

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
    # print(env_variables,'env_variables in line no 152')
    """
    Use OpenAI API to generate meaningful questions for environment variables using their keys and values.

    Args:
        env_variables (dict): A dictionary of environment variable key-value pairs.

    Returns:
        list: A list of generated questions.
    """
    # Create a prompt using key-value pairs
    prompt = "For the following environment variables, generate one question per key-value pair. Do not include any extra text or introduction, only the questions:\n\n"
    for key, value in env_variables.items():
        prompt += f"- {key} with value {value}\n"
    # print(f"Prompt: {prompt}")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
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

    if matches:
        for var_name, var_optional in matches:
            # Categorize based on the 'optional' field
            if var_optional == 'true':
                non_mandatory.append(var_name)
            else:
                mandatory.append(var_name)

        return {"mandatory": mandatory, "non_mandatory": non_mandatory}

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

    # Fetch env files
    env_url = SERVICE_URLS[service_name]
    variables_url = ENV_VARIABLES_URLS[service_name]

    env_content = fetch_file_content(env_url)
    variables_content = fetch_file_content(variables_url)

    if not env_content or "Error" in env_content:
        return render_template('home.html', services=SERVICE_URLS.keys(),
                               error_message=f"Error fetching .env file: {env_content}")
    
    # Parse .env and JavaScript variables
    env_variables = parse_env_file(env_content)
    parsed_variables = parse_env_variables_js(variables_content)

    # Generate questions using key-value pairs
    mandatory_questions = generate_questions({
        name: env_variables.get(name, "Not defined")
        for name in parsed_variables.get('mandatory', [])
    })

    non_mandatory_questions = generate_questions({
        name: env_variables.get(name, "Not defined")
        for name in parsed_variables.get('non_mandatory', [])
    })

    # Combine variables and questions
    combined_variables = {
        "mandatory": [
            {
                "name": name,
                "question": question,
                "value": env_variables.get(name, "Not defined")
            }
            for name, question in zip(parsed_variables.get('mandatory', []), mandatory_questions)
        ],
        "non_mandatory": [
            {
                "name": name,
                "question": question,
                "value": env_variables.get(name, "Not defined")
            }
            for name, question in zip(parsed_variables.get('non_mandatory', []), non_mandatory_questions)
        ]
    }

    # Store data in session
    session['mandatory'] = combined_variables['mandatory']
    session['non_mandatory'] = combined_variables['non_mandatory']
    session['env_sample'] = parsed_variables
    return redirect(url_for('questions'))


@app.route('/questions', methods=['GET', 'POST'])
def questions():
    mandatory_questions = session.get('mandatory', [])
    non_mandatory_questions = session.get('non_mandatory', [])
    user_answers = session.get('user_answers', {})
    for question in mandatory_questions + non_mandatory_questions:
        
        if question['name'] not in user_answers:
            print('user_answers not there', question['name'] )
            user_answers[question['name']] = question['value']
        else:
            print(f"Key '{question['name']}' already exists with value: {user_answers[question['name']]}")

    if request.method == 'POST':
        # Update user answers in the session
        for question in mandatory_questions + non_mandatory_questions:
            user_answers[question['name']] = request.form.get(question['name'], '')
        
        # Save user answers to session
        session['user_answers'] = user_answers

        return redirect(url_for('generate'))

    return render_template(
        'questions.html',
        mandatory_questions=mandatory_questions,
        non_mandatory_questions=non_mandatory_questions,
        user_answers=user_answers
    )

@app.route('/generate', methods=['GET'])
def generate():
    user_answers = session.get('user_answers', {})

    base_env_vars = {
        "CLOUD_STORAGE_PROVIDER": os.getenv('CLOUD_STORAGE_PROVIDER'),
        "CLOUD_STORAGE_ACCOUNTNAME": os.getenv('CLOUD_STORAGE_ACCOUNTNAME'),
        "CLOUD_STORAGE_SECRET": os.getenv('CLOUD_STORAGE_SECRET'),
        "CLOUD_STORAGE_REGION": os.getenv('CLOUD_STORAGE_REGION'),
        "CLOUD_ENDPOINT": os.getenv('CLOUD_ENDPOINT'),
        "CLOUD_STORAGE_BUCKETNAME": os.getenv('CLOUD_STORAGE_BUCKETNAME'),
        "PUBLIC_ASSET_BUCKETNAME": os.getenv('PUBLIC_ASSET_BUCKETNAME'),
        "CLOUD_STORAGE_BUCKET_TYPE": os.getenv('CLOUD_STORAGE_BUCKET_TYPE')
    }

    final_env_vars = {**base_env_vars, **user_answers}

    env_lines = [f"{key}={value}" for key, value in final_env_vars.items()]
    env_content = "\n".join(env_lines)

    # Creating a BytesIO object for the .env file
    env_file = BytesIO()
    env_file.write(env_content.encode('utf-8'))
    env_file.seek(0)

    # Send the file as an attachment with the correct .env name
    return send_file(env_file, as_attachment=True, download_name=".env", mimetype='text/plain')

def validate_env_variables():
    """
    Validate that all required environment variables are set.
    If any variable is missing, raise an error and provide a table format.
    """
    required_env_vars = [
        "SECRET_KEY",
        "OPENAI_API_KEY",
        "CLOUD_STORAGE_PROVIDER",
        "CLOUD_STORAGE_ACCOUNTNAME",
        "CLOUD_STORAGE_SECRET",
        "CLOUD_STORAGE_REGION",
        "CLOUD_ENDPOINT",
        "CLOUD_STORAGE_BUCKETNAME",
        "PUBLIC_ASSET_BUCKETNAME",
        "CLOUD_STORAGE_BUCKET_TYPE"
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        # Create a table format for missing variables
        table_header = f"{'Variable Name':<30} | {'Description':<40}\n" + "-" * 73
        table_rows = "\n".join([f"{var:<30} | {'Set this variable in the .env file':<40}" for var in missing_vars])
        table_message = f"{table_header}\n{table_rows}"

        # Raise an error with only the table format
        raise EnvironmentError(f"\n{table_message}")


# Call the validation function before starting the app
try:
    validate_env_variables()
except EnvironmentError as e:
    print(e)  # Cleanly print the error message (the table in this case)
    exit(1)  

if __name__ == '__main__':
    app.run(debug=True)
