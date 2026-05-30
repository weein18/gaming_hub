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
import re
import dns.resolver
from datetime import datetime, timedelta
import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler




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

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'elitehub040@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'qhtsdaclltewmwwd')

mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

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
    is_admin = db.Column(db.Boolean, default=False)
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
    predictions = db.relationship('Prediction', backref='match', lazy=True)
    def is_started(self):
        try:
            germany_tz = pytz.timezone('Europe/Berlin')
            now = datetime.now(germany_tz).replace(tzinfo=None)
            clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', self.date.strip())
            t_str = self.time.strip()
            if ':' in t_str:
                h, m = t_str.split(':')
                t_str = f"{int(h):02d}:{int(m):02d}"
            match_dt = datetime.strptime(f"{clean_date} 2026 {t_str}", "%B %d %Y %H:%M")
            print(f"--- MATCH {self.id} --- Germany Now: {now} | Match Time: {match_dt}")
            return now >= match_dt
        except Exception as e:
            print(f"!!! TIME ERROR: {e}")
            return False
class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    prize_pool = db.Column(db.String(50))
    date = db.Column(db.String(50))
    xp_reward = db.Column(db.String(50))
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

@app.after_request
def add_security_headers(response):
    # defens (Clickjacking)
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # defens( MIME-sniffing)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # filter XSS on old
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Content Security Policy (CSP)
    # defens against XSS
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
    return response

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        username = re.sub('<[^<]+?>', '', username)
        email = request.form.get('email', '').strip().lower()
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            flash("Please enter a valid email address (e.g. name@gmail.com)!")
            return redirect(url_for('register'))
        domain = email.split('@')[-1]
        try:
            dns.resolver.resolve(domain, 'MX')
        except Exception:
            flash("This email domain does not exist! Use a real provider like Gmail.")
            return redirect(url_for('register'))
        fav_team = request.form.get('favorite_team', '').strip()
        fav_team = re.sub('<[^<]+?>', '', fav_team)
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        if not username:
            flash("Username is required!")
            return redirect(url_for('register'))
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
    upcoming_tournament_names = db.session.query(Match.tournament_name).filter(
        Match.status == 'Upcoming'
    ).distinct().all()
    active_names = [t[0] for t in upcoming_tournament_names]
    active_tournaments = Tournament.query.filter(Tournament.name.in_(active_names)).all()
    return render_template('games/matches.html', tournaments=active_tournaments)

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
        new_username = re.sub('<[^<]+?>', '', new_username).strip()
        if new_username != current_user.username:
            user_exists = User.query.filter_by(username=new_username).first()
            if user_exists:
                flash("This username is already taken!")
                return redirect(url_for('settings'))
            current_user.username = new_username
        raw_steam_url = request.form.get('steam_url', '').strip()
        if raw_steam_url:
            if raw_steam_url.startswith('https://steamcommunity.com/'):
                current_user.steam_url = raw_steam_url
            else:
                current_user.steam_url = ""
                flash("Invalid Steam URL! Only official Steam links allowed.")
        else:
            current_user.steam_url = ""
        raw_bio = request.form.get('bio', '')
        current_user.bio = re.sub('<[^<]+?>', '', raw_bio).strip()
        raw_team = request.form.get('favorite_team', '')
        current_user.favorite_team = re.sub('<[^<]+?>', '', raw_team).strip()
        current_user.email = request.form.get('email')
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
    all_user_preds = Prediction.query.filter_by(user_id=user.id).order_by(Prediction.id.desc()).all()
    win_streak = 0
    for pred in all_user_preds:
        if pred.is_correct is True:
            win_streak += 1
        elif pred.is_correct is False:
            break
        else:
            continue
    xp = user.xp
    if xp >= 9500:   
        user.rank, next_rank, current_threshold, next_threshold = 'The Global Elite', 'MAX', 9500, 10000
    elif xp >= 8900: 
        user.rank, next_rank, current_threshold, next_threshold = 'Supreme Master First Class', 'The Global Elite', 8900, 9500
    elif xp >= 8300: 
        user.rank, next_rank, current_threshold, next_threshold = 'Legendary Eagle Master', 'Supreme Master First Class', 8300, 8900
    elif xp >= 7700: 
        user.rank, next_rank, current_threshold, next_threshold = 'Legendary Eagle', 'Legendary Eagle Master', 7700, 8300
    elif xp >= 7100: 
        user.rank, next_rank, current_threshold, next_threshold = 'Distinguished Master Guardian', 'Legendary Eagle', 7100, 7700
    elif xp >= 6500: 
        user.rank, next_rank, current_threshold, next_threshold = 'Master Guardian Elite', 'Distinguished Master Guardian', 6500, 7100
    elif xp >= 5900: 
        user.rank, next_rank, current_threshold, next_threshold = 'Master Guardian II', 'Master Guardian Elite', 5900, 6500
    elif xp >= 5300: 
        user.rank, next_rank, current_threshold, next_threshold = 'Master Guardian I', 'Master Guardian II', 5300, 5900
    elif xp >= 4700: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova Master', 'Master Guardian I', 4700, 5300
    elif xp >= 4100: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova III', 'Gold Nova Master', 4100, 4700
    elif xp >= 3500: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova II', 'Gold Nova III', 3500, 4100
    elif xp >= 2900: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova I', 'Gold Nova II', 2900, 3500
    elif xp >= 2300: 
        user.rank, next_rank, current_threshold, next_threshold = 'Silver Elite Master', 'Gold Nova I', 2300, 2900
    elif xp >= 1700: 
        user.rank, next_rank, current_threshold, next_threshold = 'Silver Elite', 'Silver Elite Master', 1700, 2300
    elif xp >= 1100: 
        user.rank, next_rank, current_threshold, next_threshold = 'Silver IV', 'Silver Elite', 1100, 1700
    elif xp >= 600:  
        user.rank, next_rank, current_threshold, next_threshold = 'Silver III', 'Silver IV', 600, 1100
    elif xp >= 300:  
        user.rank, next_rank, current_threshold, next_threshold = 'Silver II', 'Silver III', 300, 600
    else:            
        user.rank, next_rank, current_threshold, next_threshold = 'Silver I', 'Silver II', 0, 300
    db.session.commit()
    if user.rank == 'The Global Elite':
        progress_percent = 100
    else:
        xp_in_current_level = xp - current_threshold
        level_duration = next_threshold - current_threshold
        progress_percent = int((xp_in_current_level / level_duration) * 100)
        progress_percent = max(0, min(100, progress_percent))
    featured_match = Match.query.filter_by(status="Upcoming").first()
    recent_predictions = Prediction.query.filter_by(user_id=user.id).order_by(Prediction.id.desc()).limit(10).all()
    return render_template('admin/dashboard.html', 
                           user=user, 
                           accuracy=accuracy, 
                           total_wins=correct_preds,
                           total_preds=total_preds,
                           next_rank=next_rank,
                           next_threshold=next_threshold,
                           progress_percent=progress_percent,
                           win_streak=win_streak,
                           featured_match=featured_match,
                           predictions_count=len(recent_predictions),
                           recent_predictions=recent_predictions)

@app.route('/tournament/<name>')
@login_required
def tournament(name):
    url_name = name.replace('-', ' ') 
    tournament_info = Tournament.query.filter(Tournament.name.ilike(url_name)).first()
    if tournament_info:
        real_db_name = tournament_info.name
    else:
        real_db_name = url_name
    selected_date = request.args.get('date')
    all_dates_query = db.session.query(Match.date).filter(
        Match.tournament_name.ilike(real_db_name)
    ).distinct().all()
    all_dates = [d[0] for d in all_dates_query if d[0]]
    def parse_date_string(date_str):
        try:
            clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
            return datetime.strptime(clean_date, "%B %d")
        except:
            try:
                return datetime.strptime(clean_date, "%B %d %Y")
            except:
                return datetime.min
    all_dates.sort(key=parse_date_string)
    if not selected_date and all_dates:
        selected_date = all_dates[0]
    tournament_matches = Match.query.filter(
        Match.tournament_name.ilike(real_db_name),
        Match.date == selected_date
    ).all()
    tournament_matches.sort(key=lambda x: datetime.strptime(x.time.strip(), '%H:%M') if ':' in x.time else x.time)
    user_predictions = Prediction.query.filter_by(user_id=current_user.id).all()
    preds_dict = {p.match_id: p.prediction_score for p in user_predictions}
    return render_template('tournament.html',
                           tournament_name=real_db_name,
                           tournament=tournament_info,
                           matches=tournament_matches,
                           all_dates=all_dates,
                           current_date=selected_date,
                           user_preds=preds_dict)

@app.route('/all-tournament')
@login_required
def all_tournaments():
    tournaments = db.session.query(Match.tournament_name).distinct().all()
    tour_list = [{"display": t[0], "url": t[0].lower().replace(' ', '-')} for t in tournaments]
    return render_template('all_tournaments.html', tournaments=tour_list)

@app.route('/admin/add_match', methods=['GET', 'POST'])
@login_required
def add_match():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if request.method == 'POST':
        t_name = request.form.get('tournament')
        t1 = request.form.get('team1')
        t2 = request.form.get('team2')
        m_date = request.form.get('date')
        m_time = request.form.get('time')
        m_type = request.form.get('match_type')
        new_match = Match(
            tournament_name=t_name,
            team1=t1,
            team2=t2,
            date=m_date,
            time=m_time,
            match_type=m_type
        )
        db.session.add(new_match)
        db.session.commit()
        flash('Match added successfully!', 'success')
        return redirect(url_for('add_match'))
    all_tournaments = Tournament.query.all()
    return render_template('admin/add_match.html', tournaments=all_tournaments)

@app.route("/admin/add_tournament", methods=["GET", "POST"])
@login_required
def add_tournament():
        if not current_user.is_admin:
            flash("Only admin page!!!")
            return redirect(url_for("index"))
        if request.method == 'POST':
            new_t = Tournament(
                name=request.form.get('name'),
                prize_pool=request.form.get('prize_pool'),
                date=request.form.get('date'),
                xp_reward=request.form.get('xp_reward') 
            )
            db.session.add(new_t)
            db.session.commit()
            return redirect(url_for('matches'))
        return render_template('admin/add_tournament.html')

@app.route('/predict/<int:match_id>', methods=['POST'])
@login_required
def predict(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status != 'Upcoming' or match.is_started():
        flash("Too late! The match has already started or finished.")
        return redirect(request.referrer)
    score = request.form.get('predicted_score') 
    existing = Prediction.query.filter_by(user_id=current_user.id, match_id=match_id).first()
    if existing:
        existing.prediction_score = score
    else:
        new_pred = Prediction(user_id=current_user.id, match_id=match_id, prediction_score=score)
        db.session.add(new_pred)
    db.session.commit()
    flash("Prediction saved!")
    return redirect(request.referrer)

@app.route('/admin/manage-matches')
def manage_matches():
    if not current_user.is_admin:
        flash("Only admins can access this page!")
        return redirect(url_for("index"))
    active_matches = Match.query.filter_by(status='Upcoming').all()
    return render_template('admin/manage_matches.html', active_matches=active_matches)

@app.route('/admin/close-match/<int:match_id>', methods=['POST'])
@login_required
def close_match(match_id):
    if not current_user.is_admin:
        flash("Only admin access!!!")
        return redirect(url_for("index"))
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
                if user:
                    user.xp += 100
                else:
                    print(f"Warning: User with ID {pred.user_id} not found for prediction {pred.id}")
        db.session.commit()
        flash(f"Match {match.team1} vs {match.team2} closed with score {final_score}!") 
    return redirect(url_for('manage_matches'))

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

@app.route('/request-password-reset', methods=['POST'])
@login_required
def request_password_reset():
    email = current_user.email
    user = User.query.filter_by(email=email).first()
    if user:
        token = s.dumps(email, salt='password-reset-salt')
        link = url_for('reset_password', token=token, _external=True)
        
        try:
            msg = Message(
                subject='Password Reset Request — Command Center', 
                sender=app.config['MAIL_USERNAME'], 
                recipients=[email]
            )
            msg.body = f'''Hello {user.username},

You requested a password reset from your Command Center dashboard. 
To pick a new password, click on the link below:

{link}

This link will expire in 30 minutes. If you did not make this request, simply ignore this email.
'''
            mail.send(msg)
            flash("Check your email inbox! We have dispatched a secure reset link.", "success")
        except Exception as e:
            print(f"!!! MAIL SENDING ERROR: {e}")
            flash("Failed to send mail. Please verify mail server configuration.", "danger")
    else:
        flash("Account security context error. User not found.", "danger")
    return redirect(url_for('dashboard'))

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except Exception as e:
        print(f"!!! INVALID OR EXPIRED TOKEN: {e}")
        flash("The reset link is invalid or has expired.", "danger")
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_pass = request.form.get('password')
        confirm_pass = request.form.get('confirm_password')
        if not new_pass or len(new_pass) < 8:
            flash("New password is too short! Minimum 8 characters required.", "danger")
            return render_template('auth/reset_password_form.html')
        if new_pass != confirm_pass:
            flash("Passwords do not match!", "danger")
            return render_template('auth/reset_password_form.html')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_pass, method='pbkdf2:sha256')
            db.session.commit()
            flash("Your password has been successfully updated! Please log in.", "success")
            return redirect(url_for('login'))
    return render_template('auth/reset_password_form.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            token = s.dumps(email, salt='password-reset-salt')
            link = url_for('reset_password', token=token, _external=True)
            
            try:
                msg = Message(
                    subject='Password Reset Request — Elite Hub',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[email]
                )
                msg.body = f"Hello {user.username},\n\nTo reset your password, please click the secure link below:\n\n{link}\n\nThis link is valid for 30 minutes."
                mail.send(msg)
                flash("A secure recovery link has been sent to your email inbox.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                print(f"!!! MAIL SENDING ERROR: {e}")
                flash("Mail transmission failure. Please try again later.", "danger")
        else:
            flash("If this email exists in our system, a reset link has been dispatched.", "success")
            return redirect(url_for('login'))
            
    return render_template('auth/forgot_password.html')

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

from datetime import datetime, timedelta

@app.route('/user/<username>/history')
@login_required
def user_history(username):
    user = User.query.filter_by(username=username).first_or_404()
    t_filter = request.args.get('tournament')
    time_range = request.args.get('range')
    query = Prediction.query.filter_by(user_id=user.id).join(Match)
    if time_range == 'week':
        one_week_ago = datetime.now() - timedelta(days=7)
        query = query.filter(Match.date >= one_week_ago) 
    elif time_range == 'month':
        one_month_ago = datetime.now() - timedelta(days=30)
        query = query.filter(Match.date >= one_month_ago)
    if t_filter:
        query = query.filter(Match.tournament_name == t_filter)
    predictions = query.order_by(Match.id.desc()).all()
    all_t = db.session.query(Match.tournament_name).distinct().all()
    tournaments = [t[0] for t in all_t if t[0]]
    return render_template('user/user_history.html', 
                           user=user, 
                           predictions=predictions, 
                           tournaments=tournaments,
                           selected_tournament=t_filter,
                           selected_range=time_range)

@app.after_request
def add_security_headers(response):
    # clickjcking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # content guess
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # CSP
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
    # (Strict-Transport-Security)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

def auto_fetch_pandascore_matches():
    token = "sBI07XYqWh_1MfcJn6b_O5rb-JkQZWtw_roTnEvAyntaRUVAKlg"
    url = f"https://api.pandascore.co/csgo/matches/upcoming?token={token}&per_page=50"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"[BG-TASK] API ERROR: {response.status_code}")
            return
        matches = response.json()
        print(f"[BG-TASK] !!! {len(matches)} matches were donwloaded from PandaScore !!!")
        with app.app_context():
            for item in matches:
                if not item.get('opponents') or len(item['opponents']) < 2:
                    continue
                league_tier = item.get('league', {}).get('tier')
                if league_tier not in ['s', 'a']:
                    continue
                api_league_name = item['league']['name'].strip()
                league_logo = item['league'].get('image_url') or "/static/images/default-tournament.png"
                api_prize = item.get('series', {}).get('prize_pool')
                final_prize_pool = f"${api_prize}" if api_prize else "TBD"
                existing_tournament = Tournament.query.filter(Tournament.name.ilike(api_league_name)).first()
                if existing_tournament:
                    final_tournament_name = existing_tournament.name
                    if final_prize_pool != "TBD" and existing_tournament.prize_pool == "TBD":
                        existing_tournament.prize_pool = final_prize_pool
                    # existing_tournament.image_url = league_logo
                else:
                    new_t = Tournament(
                        name=api_league_name, 
                        prize_pool=final_prize_pool, 
                        date="Ongoing", 
                        xp_reward="100 XP"
                        # image_url=league_logo
                    )
                    db.session.add(new_t)
                    db.session.commit()
                    final_tournament_name = new_t.name
                if not item.get('begin_at'):
                    continue
                utc_time = datetime.strptime(item['begin_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                local_time = utc_time.astimezone(pytz.timezone('Europe/Berlin'))
                date_str = local_time.strftime("%B %d")  
                time_str = local_time.strftime("%H:%M")  
                match_type_str = f"BO{item.get('number_of_games', 3)}"
                existing_match = Match.query.filter_by(
                    team1=item["opponents"][0]["opponent"]["name"], 
                    team2=item["opponents"][1]["opponent"]["name"], 
                    date=date_str, 
                    time=time_str
                ).first()
                if not existing_match:
                    new_match = Match(
                        tournament_name=final_tournament_name,
                        team1=item["opponents"][0]["opponent"]["name"], 
                        team2=item["opponents"][1]["opponent"]["name"],
                        date=date_str, 
                        time=time_str,
                        match_type=match_type_str, 
                        status="Upcoming"
                    )
                    db.session.add(new_match)
                    print(f"[BG-TASK] Добавлен топовый матч: {new_match.team1} vs {new_match.team2}")
            db.session.commit()
            print("[BG-TASK] DATABASE WAS UPDATED")
    except Exception as e:
        print(f"[BG-TASK] ERROR: {e}")
scheduler = BackgroundScheduler()
scheduler.add_job(func=auto_fetch_pandascore_matches, trigger="interval", hours=12)
scheduler.start()

@app.route('/test-api-now')
def test_api_now():
    try:
        token = "sBI07XYqWh_1MfcJn6b_O5rb-JkQZWtw_roTnEvAyntaRUVAKlg"
        url = f"https://api.pandascore.co/csgo/matches/past?token={token}&per_page=50"
        response = requests.get(url, timeout=10)
        matches = response.json()
        print(f"=== ADDING MATCHES: {len(matches)}) ===")
        for item in matches:
            if not item.get('opponents') or len(item['opponents']) < 2:
                continue
            league_tier = item.get('league', {}).get('tier')
            api_league_name = item['league']['name'].strip()
            if league_tier in ['s', 'a']:
                league_logo = item['league'].get('image_url')
                api_prize = item.get('series', {}).get('prize_pool')
                final_prize_pool = f"${api_prize}" if api_prize else "TBD"
                print(f"[ПОДХОДИТ] Турнир: {api_league_name} | Тир: {league_tier.upper()} | Призовой: {final_prize_pool}")
                print(f"Ссылка на логотип: {league_logo}")
                print("-" * 40)
        print("=== THE END OF THE TEST ===")
        return "Тест запущен! Открывай логи Render и смотри, как подтягиваются логотипы и призовые.", 200
    except Exception as e:
        return f"Ошибка при тесте: {e}", 500

if __name__ == '__main__':
    auto_fetch_pandascore_matches()
    app.run(debug=False)