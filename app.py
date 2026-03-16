from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello from vulnerable container! This container is intentionally vulnerable for testing purposes. Do not use it in production environments."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)