from flask import Flask, request, render_template, jsonify, send_file
import os
import requests
from dotenv import dotenv_values
import io

app = Flask(__name__)

# Route to render the form
@app.route('/')
def index():
    return render_template('form.html')

# API to fetch and parse .env from GitHub URL
@app.route('/fetch-env', methods=['POST'])
def fetch_env():
    try:
        data = request.json
        github_url = data.get('github_url')

        # Parse GitHub URL
        if not github_url.endswith('.env.sample'):
            return jsonify({"error": "Invalid .env file URL"}), 400

        response = requests.get(github_url)
        print(response,'response')
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch .env file"}), 400

        env_content = response.text
        env_variables = dotenv_values(stream=io.StringIO(env_content))
        print(env_variables,'env_variables')
        return jsonify({"env": env_variables}), 200
    except Exception as e:
        print(e,'kkkkkkkkkkk')
        return jsonify({"error": str(e)}), 500

# API to generate a new .env file
@app.route('/update-env', methods=['POST'])
def update_env():
    try:
        data = request.json
        updated_env = data.get('env')

        # Generate .env file content
        env_content = "\n".join(f"{key}={value}" for key, value in updated_env.items())

        # Save file locally
        output_path = "updated.env"
        with open(output_path, 'w') as f:
            f.write(env_content)

        return jsonify({"message": "Env file generated successfully!", "file_path": output_path}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to download the .env file
@app.route('/download-env', methods=['GET'])
def download_env():
    file_path = "updated.env"
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
