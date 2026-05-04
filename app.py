from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import base64
from sqlalchemy import or_



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
    rank = db.Column(db.String(100), default='Silver')
    bio = db.Column(db.String(200), default='No bio yet...')
    steam_url = db.Column(db.String(200), default='')
    email = db.Column(db.String(200), unique=True, nullable=False)
    favorite_team = db.Column(db.String(50), default=' ')
    avatar = db.Column(db.Text, default='default.png')
class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_name = db.Column(db.String(100), nullable=False, default='BLAST Rivals 2026 Season 1')
    team1 = db.Column(db.String(50), nullable=False)
    team2 = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='Upcoming')
    final_score = db.Column(db.String(10), default='')
    match_type = db.Column(db.String(10), default="BO3")
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
    active_tournaments = db.session.query(Match.tournament_name).filter(
        Match.status == 'Upcoming'
    ).distinct().all()
    tournaments = []
    for t in active_tournaments:
        name = t[0]
        tournaments.append({
            'display_name': name,
            'url_name': name.lower().replace(' ', '-')
        })   
    return render_template('games/matches.html', tournaments=tournaments)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    total_preds = Prediction.query.filter_by(user_id=user.id).count()
    correct_preds = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
    if total_preds > 0:
        accuracy = int((correct_preds / total_preds) * 100)
    else:
        accuracy = 0
    xp = user.xp
    if xp >= 9500:   user.rank = 'The Global Elite'
    elif xp >= 8900: user.rank = 'Supreme Master First Class'
    elif xp >= 8300: user.rank = 'Legendary Eagle Master'
    elif xp >= 7700: user.rank = 'Legendary Eagle'
    elif xp >= 7100: user.rank = 'Distinguished Master Guardian'
    elif xp >= 6500: user.rank = 'Master Guardian Elite'
    elif xp >= 5900: user.rank = 'Master Guardian II'
    elif xp >= 5300: user.rank = 'Master Guardian I'
    elif xp >= 4700: user.rank = 'Gold Nova Master'
    elif xp >= 4100: user.rank = 'Gold Nova III'
    elif xp >= 3500: user.rank = 'Gold Nova II'
    elif xp >= 2900: user.rank = 'Gold Nova I'
    elif xp >= 2300: user.rank = 'Silver Elite Master'
    elif xp >= 1700: user.rank = 'Silver Elite'
    elif xp >= 1100: user.rank = 'Silver IV'
    elif xp >= 600:  user.rank = 'Silver III'
    elif xp >= 300:  user.rank = 'Silver II'
    else:            user.rank = 'Silver I'
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
                img_data = file.read()
                base64_encoded = base64.b64encode(img_data).decode('utf-8')
                current_user.avatar = f"data:{file.content_type};base64,{base64_encoded}"

        db.session.commit()
        flash('Profile settings saved!')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('user/settings.html', user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user
    total_preds = Prediction.query.filter_by(user_id=user.id).count()
    correct_preds = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
    accuracy = int((correct_preds / total_preds) * 100) if total_preds > 0 else 0
    xp = user.xp
    if xp >= 9500:   
        user.rank, next_rank, next_threshold = 'The Global Elite', 'MAX', 10000
    elif xp >= 8900: 
        user.rank, next_rank, next_threshold = 'Supreme Master First Class', 'The Global Elite', 9500
    elif xp >= 8300: 
        user.rank, next_rank, next_threshold = 'Legendary Eagle Master', 'Supreme Master First Class', 8900
    elif xp >= 7700: 
        user.rank, next_rank, next_threshold = 'Legendary Eagle', 'Legendary Eagle Master', 8300
    elif xp >= 7100: 
        user.rank, next_rank, next_threshold = 'Distinguished Master Guardian', 'Legendary Eagle', 7700
    elif xp >= 6500: 
        user.rank, next_rank, next_threshold = 'Master Guardian Elite', 'Distinguished Master Guardian', 7100
    elif xp >= 5900: 
        user.rank, next_rank, next_threshold = 'Master Guardian II', 'Master Guardian Elite', 6500
    elif xp >= 5300: 
        user.rank, next_rank, next_threshold = 'Master Guardian I', 'Master Guardian II', 5900
    elif xp >= 4700: 
        user.rank, next_rank, next_threshold = 'Gold Nova Master', 'Master Guardian I', 5300
    elif xp >= 4100: 
        user.rank, next_rank, next_threshold = 'Gold Nova III', 'Gold Nova Master', 4700
    elif xp >= 3500: 
        user.rank, next_rank, next_threshold = 'Gold Nova II', 'Gold Nova III', 4100
    elif xp >= 2900: 
        user.rank, next_rank, next_threshold = 'Gold Nova I', 'Gold Nova II', 3500
    elif xp >= 2300: 
        user.rank, next_rank, next_threshold = 'Silver Elite Master', 'Gold Nova I', 2900
    elif xp >= 1700: 
        user.rank, next_rank, next_threshold = 'Silver Elite', 'Silver Elite Master', 2300
    elif xp >= 1100: 
        user.rank, next_rank, next_threshold = 'Silver IV', 'Silver Elite', 1700
    elif xp >= 600:  
        user.rank, next_rank, next_threshold = 'Silver III', 'Silver IV', 1100
    elif xp >= 300:  
        user.rank, next_rank, next_threshold = 'Silver II', 'Silver III', 600
    else:            
        user.rank, next_rank, next_threshold = 'Silver I', 'Silver II', 300
    db.session.commit()
    recent_predictions = Prediction.query.filter_by(user_id=user.id).order_by(Prediction.id.desc()).limit(10).all()
    return render_template('admin/dashboard.html', 
                           user=user, 
                           accuracy=accuracy, 
                           total_wins=correct_preds,
                           next_rank=next_rank,
                           next_threshold=next_threshold,
                           predictions_count=len(recent_predictions),
                           recent_predictions=recent_predictions)

@app.route('/tournament/<name>')
@login_required
def tournament(name):
    clean_name = name.replace('-', ' ')
    selected_date = request.args.get('date')
    all_dates = db.session.query(Match.date).filter(
        Match.tournament_name.ilike(f"%{clean_name}%")
    ).distinct().order_by(Match.date.asc()).all()
    all_dates = [d[0] for d in all_dates]
    if not selected_date and all_dates:
        selected_date = all_dates[0]
    matches = Match.query.filter(
        Match.tournament_name.ilike(f"%{clean_name}%"),
        Match.date == selected_date
    ).all()
    return render_template('tournament.html', 
                           tournament_name=name, 
                           matches=matches, 
                           all_dates=all_dates, 
                           current_date=selected_date)

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
            m_type = request.form.get("match_type", "BO3")
            new_match = Match(
                tournament_name=request.form.get('tournament').strip(),
                team1=request.form.get('team1').strip(),
                team2=request.form.get('team2').strip(),
                date=request.form.get('date'),
                time=request.form.get('time'),
                match_type = m_type
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
    # current_user.xp += 10 
    db.session.commit()
    return redirect(request.referrer)
    
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

@app.route('/leaderboard')
@login_required
def leaderboard():
    top_users = User.query.order_by(User.xp.desc()).limit(50).all()
    return render_template('user/leaderboard.html', users=top_users)

@app.route('/match/<int:match_id>')
@login_required
def match_analytics(match_id):
    match = Match.query.get_or_404(match_id)
    t1_past = Match.query.filter(
        or_(Match.team1 == match.team1, Match.team2 == match.team1),
        Match.status == "Finished",
        Match.id != match_id
    ).order_by(Match.id.desc()).limit(3).all()
    t2_past = Match.query.filter(
        or_(Match.team1 == match.team2, Match.team2 == match.team2),
        Match.status == "Finished",
        Match.id != match_id
    ).order_by(Match.id.desc()).limit(3).all()
    h2h = Match.query.filter(
        or_(
            (Match.team1 == match.team1) & (Match.team2 == match.team2),
            (Match.team1 == match.team2) & (Match.team2 == match.team1)
        ),
        Match.status == "Finished",
        Match.id != match_id
    ).order_by(Match.id.desc()).limit(3).all()
    return render_template ("match_analytics.html",
                            match=match,
                            t1_past=t1_past,
                            t2_past=t2_past,
                            h2h=h2h)

if __name__ == '__main__':
    app.run(debug=True)