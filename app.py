from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer



if not os.path.exists('instance'):
    os.makedirs('instance')

app = Flask(__name__)

ADMIN_ACCESS_KEY = os.getenv('ADMIN_ACCESS_KEY')
uri = os.getenv('DATABASE_URL', 'sqlite:///database.db')
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SECRET_KEY'] = os.getenv('SECRET_ACCESS_KEY', 'default_local_secret')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# app.config.update(
#     MAIL_SERVER='smtp.gmail.com',
#     MAIL_PORT=587,
#     MAIL_USE_TLS=True,
#     MAIL_USERNAME='your-email@gmail.com',
#     MAIL_PASSWORD='your-app-password'
# )
# mail = Mail(app)
# s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(1000), nullable=False)
    xp = db.Column(db.Integer, default=0)
    rank = db.Column(db.String(20), default='Silver')
    bio = db.Column(db.String(200), default='No bio yet...')
    steam_url = db.Column(db.String(200), default='')
    email = db.Column(db.String(200), unique=True, nullable=False)
    favorite_team = db.Column(db.String(50), default=' ')
    avatar = db.Column(db.String(200), default='default.png')
class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_name = db.Column(db.String(100), nullable=False, default='BLAST Rivals 2026 Season 1')
    team1 = db.Column(db.String(50), nullable=False)
    team2 = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='Upcoming')
    final_score = db.Column(db.String(10), default='')
class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    prize_pool = db.Column(db.String(50))
    date = db.Column(db.String(50))
class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    prediction_score = db.Column(db.String(10), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        fav_team = request.form.get('favorite_team')
        if password != confirm_password:
            flash("Passwords do not match!")
            return redirect(url_for('register'))
        user_exists = User.query.filter((User.username == username) | (User.email == email)).first()
        if user_exists:
            flash("Username or Email already exists!")
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(
            username=username, 
            email=email, 
            password=hashed_password, 
            favorite_team=fav_team
        )       
        db.session.add(new_user)
        db.session.commit()       
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
        
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    stats = {
        'total_users': User.query.count(),
        'active_matches': Match.query.filter_by(status='Upcoming').count(),
        'total_predictions': Prediction.query.count()
    }
    featured_matches = Match.query.filter_by(status='Upcoming').limit(3).all()    
    return render_template('index.html', stats=stats, featured_matches=featured_matches)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')       
        user = User.query.filter_by(username=username).first()      
        if user:
            is_valid = check_password_hash(user.password, password)
            if is_valid:
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('WRONG PASSWORD!')
                print(f"User {username} exists, but password {password} is wrong for hash {user.password}")
        else:
            flash('USER NOT FOUND!')
            print(f"User {username} not found in database.")
    return render_template('auth/login.html')

@app.route('/matches')
def matches():
    unique_tournaments = db.session.query(Match.tournament_name).distinct().all()    
    tournaments = []
    for t in unique_tournaments:
        name = t[0]
        tournaments.append({
            'display_name': name,
            'url_name': name.lower().replace(' ', '-') # "IEM Rio" -> "iem-rio"
        })   
    return render_template('games/matches.html', tournaments=tournaments)

@app.route('/profile/<username>') # Добавили <username> в путь
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    total_preds = Prediction.query.filter_by(user_id=user.id).count()
    correct_preds = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
    accuracy = 0
    if total_preds > 0:
        accuracy = round((correct_preds / total_preds) * 100)
    if user.xp > 1000:
        user.rank = 'Global Elite'
    elif user.xp > 500:
        user.rank = 'Gold Nova'
    else:
        user.rank = 'Silver'
    db.session.commit()
    return render_template('user/profile.html', 
                           user=user, 
                           accuracy=accuracy, 
                           total_wins=correct_preds)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        old_pass = request.form.get('old_password')
        new_pass = request.form.get('new_password')
        confirm_pass = request.form.get('confirm_password')
        if old_pass and new_pass:
            if not check_password_hash(current_user.password, old_pass):
                flash("Old password incorrect!")
                return redirect(url_for('settings'))
            if new_pass != confirm_pass:
                flash("New passwords do not match!")
                return redirect(url_for('settings'))
            if len(new_pass) < 6:
                flash("New password is too short!")
                return redirect(url_for('settings'))
            current_user.password = generate_password_hash(new_pass)
            flash("Password security updated!")
        new_username = request.form.get('username')
        if new_username != current_user.username:
            user_exists = User.query.filter_by(username=new_username).first()
            if user_exists:
                flash("This username is already taken!")
                return redirect(url_for('settings'))
            current_user.username = new_username
        current_user.email = request.form.get('email')
        current_user.bio = request.form.get('bio')
        current_user.steam_url = request.form.get('steam_url')
        current_user.favorite_team = request.form.get('favorite_team')
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"user_{current_user.id}.{ext}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.avatar = filename

        db.session.commit()
        flash('Profile settings saved!')
        return redirect(url_for('profile', username=current_user.username))

    return render_template('user/settings.html')

@app.route('/dashboard')
@login_required
def dashboard():
    recent_predictions = Prediction.query.filter_by(user_id=current_user.id).limit(10).all()
    weekly_xp = current_user.xp
    return render_template('admin/dashboard.html', weekly_xp=weekly_xp, predictions_count=len(recent_predictions))

@app.route('/tournament/<name>')
@login_required
def tournament(name):
    clean_name = name.replace('-', ' ')
    tournament_matches = Match.query.filter(
        Match.tournament_name.ilike(f"%{clean_name}%"),
        Match.status == 'Upcoming'
    ).all()     
    user_predictions = Prediction.query.filter_by(user_id=current_user.id).all()    
    preds_dict = {p.match_id: p.prediction_score for p in user_predictions}    
    return render_template('tournament.html', 
                           tournament_name=name, 
                           matches=tournament_matches, 
                           user_preds=preds_dict)

@app.route('/all-tournament')
@login_required
def all_tournaments():
    tournaments = db.session.query(Match.tournament_name).distinct().all()
    tour_list = [{"display": t[0], "url": t[0].lower().replace(' ', '-')} for t in tournaments]
    return render_template('all_tournaments.html', tournaments=tour_list)

@app.route('/admin/add_match', methods=['GET', 'POST'])
def admin_add_match():
        key = request.args.get('key')
        if key != ADMIN_ACCESS_KEY:
            return "Access Denied: Wrong or missing key.", 403
        if request.method == 'POST':
            new_match = Match(
                tournament_name=request.form.get('tournament').strip(),
                team1=request.form.get('team1').strip(),
                team2=request.form.get('team2').strip(),
                date=request.form.get('date'),
                time=request.form.get('time')
            )
            db.session.add(new_match)
            db.session.commit()
            return redirect(url_for('admin_add_match', key=ADMIN_ACCESS_KEY))
        return render_template('/admin/add_match.html', access_key=ADMIN_ACCESS_KEY)

@app.route('/predict/<int:match_id>', methods=['POST'])
@login_required
def predict(match_id):
    score = request.form.get('predicted_score') 
    existing = Prediction.query.filter_by(user_id=current_user.id, match_id=match_id).first()
    if existing:
        existing.prediction_score = score
    else:
        new_pred = Prediction(user_id=current_user.id, match_id=match_id, prediction_score=score)
        db.session.add(new_pred)
    current_user.xp += 10 
    db.session.commit()
    return redirect(request.referrer)

# @app.route('/admin/finish_match/<int:match_id>')
# @login_required
# def finish_match(match_id):
#     match = db.session.get(Match, match_id)
#     if match:
#         match.status = "Finished"
#         db.session.commit()
#     return redirect(request.referrer or url_for('matches'))
    
@app.route('/admin/manage-matches')
def manage_matches(): 
    key = request.args.get('key')
    if key != ADMIN_ACCESS_KEY:
        return "Access Denied: Wrong or missing key.", 403
    active_matches = Match.query.filter_by(status='Upcoming').all()
    return render_template('admin/manage_matches.html', active_matches=active_matches, access_key=ADMIN_ACCESS_KEY)

@app.route('/admin/close-match/<int:match_id>', methods=['POST'])
@login_required
def close_match(match_id):
    key = request.args.get('key')
    if key != ADMIN_ACCESS_KEY:
        return "Unauthorized", 403
    final_score = request.form.get('final_score')
    match = db.session.get(Match, match_id)   
    if match and final_score:
        match.final_score = final_score
        match.status = 'Finished'        
        predictions = Prediction.query.filter_by(match_id=match_id).all()
        for pred in predictions:
            if pred.prediction_score == final_score:
                pred.is_correct = True
                user = db.session.get(User, pred.user_id)
                user.xp += 100
        db.session.commit()
        flash(f"Match {match.team1} vs {match.team2} closed with score {final_score}!") 
    return redirect(url_for('manage_matches', key=ADMIN_ACCESS_KEY))

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

# @app.route('/forgot-password', methods=['GET', 'POST'])
# def forgot_password():
#     if request.method == 'POST':
#         email = request.form.get('email')
#         user = User.query.filter_by(email=email).first()
#         if user:
#             token = s.dumps(email, salt='email-confirm')
#             link = url_for('reset_password', token=token, _external=True)
#             msg = Message('Password Reset Request', 
#                           sender='your-email@gmail.com', 
#                           recipients=[email])
#             msg.body = f'Your link to reset password: {link}'
#             mail.send(msg)
#             flash("Check your email! Reset link sent.")
#         else:
#             flash("User with this email not found.")
#     return render_template('auth/forgot_password.html')

# @app.route('/reset-password/<token>', methods=['GET', 'POST'])
# def reset_password(token):
#     try:
#         email = s.loads(token, salt='password-reset-salt', max_age=1800)
#     except:
#         flash("The reset link is invalid or has expired.")
#         return redirect(url_for('login'))
#     if request.method == 'POST':
#         new_pass = request.form.get('password')
#         confirm_pass = request.form.get('confirm_password')
#         if new_pass != confirm_pass:
#             flash("Passwords do not match!")
#             return render_template('auth/reset_password_form.html')
#         user = User.query.filter_by(email=email).first()
#         if user:
#             user.password = generate_password_hash(new_pass, method='pbkdf2:sha256')
#             db.session.commit()
#             flash("Your password has been updated!")
#             return redirect(url_for('login'))
#     return render_template('auth/reset_password_form.html')

@app.route('/secret-user-list')
def secret_users():
    users = User.query.all()
    output = "<h1>Users in Database:</h1>"
    for u in users:
        output += f"<p>ID: {u.id} | Name: {u.username} | Email: {u.email} | Team: {u.favorite_team}</p>"
    return output

if __name__ == '__main__':
    app.run(debug=True)