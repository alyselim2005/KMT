# run.py
from xml.dom.minidom import Document
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)

# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import LoginManager
import logging

# تهيئة الإضافات
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # تهيئة الإضافات
    db.init_app(app)
    login_manager.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # إعداد تسجيل الأحداث
    logging.basicConfig(filename="app.log", level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")

    # تسجيل المسارات
    from .routes.main_routes import main_routes
    from .routes.api_routes import api_routes

    app.register_blueprint(main_routes)
    app.register_blueprint(api_routes, url_prefix="/api")

    with app.app_context():
        db.create_all()

    return app

# config.py
import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# app/models.py
from . import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class GeneratedText(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    input_text = db.Column(db.Text, nullable=False)
    output_text = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('texts', lazy=True))

# app/routes/main_routes.py
from flask import Blueprint, jsonify, request, render_template
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from ..models import User
from .. import db

main_routes = Blueprint('main', __name__)

# الصفحة الرئيسية
@main_routes.route("/")
def home():
    return render_template("index.html")

# تسجيل مستخدم جديد
@main_routes.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    hashed_password = generate_password_hash(password, method='sha256')
    new_user = User(username=username, email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

# تسجيل الدخول
@main_routes.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    user = User.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        login_user(user)
        return jsonify({"message": "Login successful"}), 200

    return jsonify({"error": "Invalid credentials"}), 401

# تسجيل الخروج
@main_routes.route("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out successfully"}), 200

# app/routes/api_routes.py
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from ..models import GeneratedText
from .. import db
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging

api_routes = Blueprint('api', __name__)

# تحميل النموذج
model_name = "gpt2"
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)
logging.info("Model and tokenizer loaded successfully.")

# توليد النصوص
@api_routes.route("/generate", methods=["POST"])
@login_required
def generate_text():
    try:
        data = request.json
        input_text = data.get("input_text", "")
        if not input_text:
            return jsonify({"error": "Input text is required"}), 400

        inputs = tokenizer.encode(input_text, return_tensors="pt")
        outputs = model.generate(inputs, max_length=100, temperature=0.7)
        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

        # حفظ النصوص المُولدة في قاعدة البيانات
        new_text = GeneratedText(input_text=input_text, output_text=generated_text, user_id=current_user.id)
        db.session.add(new_text)
        db.session.commit()

        return jsonify({"generated_text": generated_text})
    except Exception as e:
        logging.error(f"Error generating text: {e}")
        return jsonify({"error": str(e)}), 500

# app/templates/index.html
<!DOCTYPE html>
<html>
<head>
    <title>Text Generator</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
</head>
<body>
    <div class="container mt-5">
        <h1>Text Generator</h1>
        <form id="generate-form">
            <div class="mb-3">
                <label for="inputText" class="form-label">Input Text</label>
                <textarea class="form-control" id="inputText" rows="3"></textarea>
            </div>
            <button type="submit" class="btn btn-primary">Generate</button>
        </form>
        <div class="mt-4" id="result"></div>
    </div>

    <script>
        document.getElementById("generate-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            const inputText = document.getElementById("inputText").value;

            const response = await fetch("/api/generate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ input_text: inputText }),
            });

            const result = await response.json();
            document.getElementById("result").innerText = result.generated_text || result.error;
        });
    </script>
</body>
</html>
