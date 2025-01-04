import os
import random
import requests
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_file
from io import BytesIO
import openai
from dotenv import load_dotenv
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')  # Use environment variable for secret key

# OpenAI API key
openai.api_key = os.getenv('SECRET_KEY')

app.config['MAX_QUESTIONS'] = int(os.getenv('MAX_QUESTIONS', 10))  # Configure max questions to ask

def convert_to_raw_url(github_url):
    """Convert GitHub file URL to raw URL."""
    # Replace 'github.com' with 'raw.githubusercontent.com' and adjust the file path
    raw_url = github_url.replace('github.com', 'raw.githubusercontent.com')
    raw_url = raw_url.replace('/blob/', '/')
    return raw_url

def fetch_env_file(github_url):
    """Fetch the content of a .env file from a GitHub URL."""
    try:
        raw_url = convert_to_raw_url(github_url)
        response = requests.get(raw_url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return str(e)

def parse_env_file(env_content):
    """Parse the .env content into a dictionary."""
    env_variables = {}
    for line in env_content.splitlines():
        line = line.strip()
        # Skip empty lines or lines that don't contain '='
        if line and '=' in line:
            try:
                key, value = line.split('=', 1)
                env_variables[key] = value
            except ValueError:
                # Log or handle lines that still don't split correctly
                print(f"Skipping invalid line: {line}")
        else:
            # Optionally log or handle lines that are empty or malformed
            print(f"Skipping empty or malformed line: {line}")
    return env_variables

# def is_html(content):
#     """Check if the content is an HTML page based on the presence of HTML doctype or tags."""
#     # Check for HTML doctype or common HTML tags to identify HTML content
#     html_patterns = [
#         r"<!DOCTYPE\s+html>",  # Doctype for HTML5
#         r"<html[^>]*>",         # Opening <html> tag
#         r"<body[^>]*>",         # Opening <body> tag
#         r"</html>",             # Closing </html> tag
#         r"</body>",             # Closing </body> tag
#     ]
    
#     # Search for any of the HTML patterns
#     if any(re.search(pattern, content, re.IGNORECASE) for pattern in html_patterns):
#         return True
#     return False

# def parse_env_file(github_url):
#     """Fetch the content of a .env file from a GitHub URL."""
#     try:
#         raw_url = convert_to_raw_url(github_url)
#         response = requests.get(raw_url)
#         response.raise_for_status()
        
#         # Check if the response is HTML (indicating invalid .env content)
#         if is_html(response.text):
#             print (is_html(response.text))
#             return "Error: The file is an HTML page, not a valid .env file."
        
#         # Optionally: Further check if content appears to be a valid .env file
#         if not any("=" in line for line in response.text.splitlines()):
#             return "Error: The file does not contain valid key-value pairs."
        
#         return response.text
#     except requests.RequestException as e:
#         return f"Error fetching .env file: {str(e)}"

def generate_questions(env_variables):
    """Use OpenAI API to generate a readable question for an environment variable."""
    # prompt = f"Create a question for key '{key}' and value '{value}'."
    prompt = "For the following environment variables, generate one question per key-value pair. Do not include any extra text or introduction, only the questions:\n\n"
    for key, value in env_variables.items():
        prompt += f"- {key} with value {value}\n"
    print(f"Prompt: {prompt}") 
    try:
        # response = openai.ChatCompletion.create(
        #     model="gpt-4o-mini",
        #     messages=[
        #         {"role": "system", "content": "You are a helpful assistant."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     max_tokens=500
        # )
        # print(f"Response: {response}") 
        # questions = response['choices'][0]['message']['content'].strip()
        # question_list = questions.split("\n")
        ['What is the value of ACCESS_TOKEN_SECRET?  ', "What is the API_DOC_URL for the application's documentation?  ", 'What is the endpoint for retrieving user profile details?  ', 'What is the minimum approval required in the application?  ', 'What types of resources are defined in RESOURCE_TYPES?  ', 'What is the region of the OCI bucket?  ', 'What is the maximum length for resource notes?  ', 'Is logging disabled in the application?  ', 'What is the URL for the Kafka server?  ', 'What authentication method is being used in the application?  ', 'What is the OCI access key ID?  ', 'What is the Azure account key?  ', 'Are observations enabled in projects?  ', 'What is the value for CLEAR_INTERNAL_CACHE?  ', 'What is the Kafka topic used for project publishing?  ', 'What is the host URL for the user service?  ', 'What is the region of the AWS bucket?  ', 'What is the endpoint for publishing templates and tasks?  ', 'Is review required before proceeding?  ', 'What is the base URL for the user service?']
        question_list = ['What is the value of ACCESS_TOKEN_SECRET?  ', "What is the API_DOC_URL for the application's documentation?  ", 'What is the endpoint for retrieving user profile details?  ', 'What is the minimum approval required in the application?  ', 'What types of resources are defined in RESOURCE_TYPES?  ', 'What is the region of the OCI bucket?  ', 'What is the maximum length for resource notes?  ', 'Is logging disabled in the application?  ', 'What is the URL for the Kafka server?  ', 'What authentication method is being used in the application?  ', 'What is the OCI access key ID?  ', 'What is the Azure account key?  ', 'Are observations enabled in projects?  ', 'What is the value for CLEAR_INTERNAL_CACHE?  ', 'What is the Kafka topic used for project publishing?  ', 'What is the host URL for the user service?  ', 'What is the region of the AWS bucket?  ', 'What is the endpoint for publishing templates and tasks?  ', 'Is review required before proceeding?  ', 'What is the base URL for the user service?']
        print(question_list,'question_list')
        return question_list
    except Exception as e:
        print(f"Error: {e}")
        return f"Enter a value for {key}."

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/fetch', methods=['POST'])
def fetch():
    github_url = request.form['github_url']
    env_content = fetch_env_file(github_url)

    if env_content.startswith('http') or "Error" in env_content:
        # Return an error message that will be displayed in the HTML
        return render_template('home.html', error_message=f"Error fetching .env file: {env_content}")

    env_variables = parse_env_file(env_content)
    print(env_variables,'hhh')
    session['env_variables'] = env_variables
    session['answers'] = {}
    session['index'] = 0  # Track the current question index
    
    # Randomly select MAX_QUESTIONS number of keys to ask
    keys = list(env_variables.keys())
    selected_keys = random.sample(keys, app.config['MAX_QUESTIONS'])
    selected_env_variables = {key: env_variables[key] for key in selected_keys}
    session['questions'] = generate_questions(selected_env_variables)
    session['selected_keys'] = selected_keys

    return redirect(url_for('questions_paginated'))

@app.route('/questions_paginated', methods=['GET', 'POST'])
def questions_paginated():
    questions = session.get('questions', [])
    selected_keys = session.get('selected_keys', [])
    env_variables = session.get('env_variables', {})
    answers = session.get('answers', {})

    page = int(request.args.get('page', 1))
    questions_per_page = 5
    start = (page - 1) * questions_per_page
    end = start + questions_per_page

    total_pages = (len(questions) + questions_per_page - 1) // questions_per_page
    current_questions = zip(selected_keys[start:end], questions[start:end])

    if request.method == 'POST':
        for key in selected_keys[start:end]:
            current_value = request.form.get(key, env_variables.get(key, ''))
            
            # Check if the current_value is 'ON', 'OFF', 'true', or 'false'
            if current_value in ['ON', 'OFF', 'true', 'false']:
                answers[key] = current_value
            else:
                # Default: Use the value from form or existing answer
                answers[key] = request.form.get(key, session['answers'].get(key, env_variables.get(key, '')))
        
        session['answers'] = answers

        if page < total_pages:
            return redirect(url_for('questions_paginated', page=page + 1))
        else:
            return redirect(url_for('generate'))

    return render_template(
        'questions_paginated.html',
        current_questions=current_questions,
        page=page,
        total_pages=total_pages,
        env_variables=env_variables
    )



@app.route('/generate', methods=['GET'])
def generate():
    env_variables = session.get('env_variables', {})
    answers = session.get('answers', {})

    # Combine all the environment variables with the user's answers
    updated_env = [
        f"{key}={answers.get(key, value)}"  # Use the user's answer if available, otherwise the default value
        for key, value in env_variables.items()
    ]

    env_content = "\n".join(updated_env)
    env_file = BytesIO()
    env_file.write(env_content.encode('utf-8'))
    env_file.seek(0)

    return send_file(env_file, as_attachment=True, download_name=".env", mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)
