from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_migrate import Migrate
from models import db, User, Deck, Card, Session, Review

import numpy as np
from datetime import datetime, timedelta
import random
import matplotlib
matplotlib.use('Agg')  # Use Agg backend which is thread-safe
import matplotlib.pyplot as plt
import scipy.stats
import os
from io import BytesIO

# ------------------- BAYESIAN MODEL -------------------

def bayesian_posterior(card, prior_alpha=1.0, prior_beta=1.0):
    ratings = card.get_ratings()
    if not ratings:
        return prior_alpha, prior_beta
    success = sum(r >= 7 for r in ratings)
    fail = sum(r < 7 for r in ratings)
    return prior_alpha + success, prior_beta + fail

def adaptive_decay(card, user_profile, base_decay=None, history_window=5):
    reviews = card.reviews
    if base_decay is None:
        base_decay = user_profile.global_decay
    if len(reviews) < 2:
        return base_decay
        
    # Get the most recent reviews
    window = sorted(reviews, key=lambda x: x.timestamp)[-history_window:]
    decay = base_decay
    
    for i in range(1, len(window)):
        t0, rating0 = window[i-1].timestamp, window[i-1].rating
        t1, rating1 = window[i].timestamp, window[i].rating
        delta_t = (t1 - t0).total_seconds() / 60
        delta_rating = rating1 - rating0
        if delta_rating < 0:
            decay += abs(delta_rating) * delta_t / 10000
        elif delta_rating > 0 and delta_t > 10:
            decay *= 0.97
            
    # reward for maturity streak
    if card.mature_streak > 3:
        decay *= 0.6
    return max(0.001, decay)

def sample_next_review(card, user_profile, target_recall=0.7, n_samples=3000):
    alpha, beta = bayesian_posterior(card)
    decay = adaptive_decay(card, user_profile)
    p0_samples = np.random.beta(alpha, beta, n_samples)
    t_samples = []
    for p0 in p0_samples:
        if p0 <= target_recall:
            t_samples.append(1)
        else:
            t = np.log(p0 / target_recall) / decay
            t_samples.append(max(1, t))
            
    # Streak/age/maturity logic: stretch for mature/old cards
    age_factor = 1 + (card.mature_streak // 2) + (card.time_since_added() / (60 * 24 * 7))
    t_samples = [t * age_factor for t in t_samples]
    
    # Add random jitter for multi-scale spacing
    interval = int(np.percentile(t_samples, np.random.uniform(30, 80)))
    return interval, t_samples

def interval_to_text(minutes):
    if minutes < 60:
        return f"{minutes} minutes"
    elif minutes < 1440:
        return f"{minutes // 60} hours"
    else:
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        return f"{days} days, {hours} hours" if hours else f"{days} days"

def get_recent_posterior(user_profile, window=30, prior_alpha=2, prior_beta=1):
    recent = user_profile.get_recall_history()[-window:]
    successes = sum(s for _, s in recent)
    failures = len(recent) - successes
    alpha = prior_alpha + successes
    beta = prior_beta + failures
    return alpha, beta

def sample_success_rate(alpha, beta, n_samples=1000):
    return np.random.beta(alpha, beta, n_samples)

def bayesian_success_rate_interval(interval, alpha, beta, target=0.8, sensitivity=0.2):
    p_samples = np.random.beta(alpha, beta, 1000)
    mean_p = np.mean(p_samples)
    correction = 1 + sensitivity * (mean_p - target)
    return int(max(1, interval * correction))

# ------------------- SCHEDULER -------------------

class Scheduler:
    def __init__(self, user_profile, cards):
        self.user_profile = user_profile
        self.cards = cards
        self.card_review_counts = {card.id: 0 for card in self.cards}  # For per-session review limits

    def select_next_card(self, backlog_limit=50, max_reviews_per_card=2):
        urgents = []
        news = []
        matures = []
        
        for c in self.cards:
            if self.card_review_counts[c.id] >= max_reviews_per_card:
                continue
            if c.review_count() == 0:
                news.append(c)
            elif not c.is_mature or (c.last_wrong and (datetime.now() - c.last_wrong).total_seconds() / 3600 < 48):
                urgents.append(c)
            else:
                matures.append(c)
                
        random.shuffle(urgents)
        random.shuffle(news)
        random.shuffle(matures)
        
        to_study = urgents[:backlog_limit] + news[:3] + matures[:5]
        if len(to_study) > backlog_limit:
            to_study = to_study[:backlog_limit]
            
        if to_study:
            card = random.choice(to_study)
            self.card_review_counts[card.id] += 1
            return card
        else:
            remaining = [c for c in self.cards if self.card_review_counts[c.id] < max_reviews_per_card]
            if remaining:
                card = random.choice(remaining)
                self.card_review_counts[card.id] += 1
                return card
            return random.choice(self.cards) if self.cards else None

# ------------------- APP CONFIGURATION -------------------

app = Flask(__name__)
CORS(app)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'flashcards.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy with the Flask app
db.init_app(app)
migrate = Migrate(app, db)

# Create default user if not exists - updated to use with_app_context
def create_default_user():
    with app.app_context():
        if not User.query.filter_by(username='default').first():
            default_user = User(username='default')
            db.session.add(default_user)
            db.session.commit()

# ------------------- API ROUTES -------------------

@app.route('/api/decks', methods=['GET', 'POST'])
def decks():
    if request.method == 'GET':
        all_decks = Deck.query.all()
        return jsonify([deck.name for deck in all_decks])
    else:
        try:
            deck_name = request.json.get('deck')
            if not deck_name:
                return jsonify({'error': 'Deck name is required'}), 400
                
            # Check if deck already exists
            if Deck.query.filter_by(name=deck_name).first():
                return jsonify({'error': 'Deck already exists'}), 409
                
            # Create new deck
            new_deck = Deck(name=deck_name)
            db.session.add(new_deck)
            db.session.commit()
            
            return jsonify({'success': True, 'message': f'Deck "{deck_name}" created successfully'})
        except Exception as e:
            # Roll back transaction in case of error
            db.session.rollback()
            print(f"Error creating deck: {str(e)}")
            return jsonify({'error': f'Failed to create deck: {str(e)}'}), 500

@app.route('/api/cards/<deck>', methods=['GET', 'POST'])
def cards(deck):
    # Find the deck
    deck_obj = Deck.query.filter_by(name=deck).first()
    if not deck_obj:
        return jsonify({'error': 'Deck not found'}), 404
        
    if request.method == 'GET':
        cards = [card.to_dict() for card in deck_obj.cards]
        return jsonify(cards)
    else:
        card_data = request.json  # {front, back, frontImage, backImage, type}
        
        # Create and store new card
        new_card = Card(
            front=card_data.get('front', ''),
            back=card_data.get('back', ''),
            front_image=card_data.get('frontImage'),
            back_image=card_data.get('backImage'),
            card_type=card_data.get('type', 'Basic')
        )
        
        # Add card to deck
        deck_obj.cards.append(new_card)
        db.session.add(new_card)
        db.session.commit()
        
        return jsonify({'success': True, 'id': new_card.id})

@app.route('/api/next_card/<deck>/<user>', methods=['POST'])
def next_card(deck, user):
    # Get or create user
    user_obj = User.query.filter_by(username=user).first()
    if not user_obj:
        user_obj = User(username=user)
        db.session.add(user_obj)
        db.session.commit()
    
    # Get deck
    deck_obj = Deck.query.filter_by(name=deck).first()
    if not deck_obj or not deck_obj.cards:
        return jsonify({'error': 'No cards in deck'}), 404
    
    # Use the scheduler to get the next card
    scheduler = Scheduler(user_obj, deck_obj.cards)
    next_card = scheduler.select_next_card()
    
    if not next_card:
        return jsonify({'error': 'No cards available'}), 404
    
    # Get interval prediction
    interval, _ = sample_next_review(next_card, user_obj)
    
    stats = {
        "next_interval": interval,
        "pomodoro_time": user_obj.pomodoro_length
    }
    
    return jsonify({**next_card.to_dict(), "stats": stats})

@app.route('/api/review/<deck>/<user>', methods=['POST'])
def review_card(deck, user):
    data = request.json
    card_id = data.get('id')
    rating = data.get('rating')
    session_id = data.get('session_id')
    
    # Get or create user
    user_obj = User.query.filter_by(username=user).first()
    if not user_obj:
        user_obj = User(username=user)
        db.session.add(user_obj)
    
    # Find the card
    card = Card.query.get(card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    
    # Use active session from the user profile if not explicitly provided
    if not session_id and user_obj.active_session_id:
        session_id = user_obj.active_session_id
    
    # Add the review
    card.add_review(rating, session_id)
    user_obj.add_recall(0, rating >= 7)  # Simple success/fail based on rating
    
    # If there's an active session, track the review there as well
    session = None
    if session_id:
        session = Session.query.get(session_id)
        if session:
            session.add_review(card_id, rating)
    
    db.session.commit()
    
    # Get the deck object
    deck_obj = Deck.query.filter_by(name=deck).first()
    if not deck_obj:
        return jsonify({'error': 'Deck not found'}), 404
    
    # Get next card using scheduler
    scheduler = Scheduler(user_obj, deck_obj.cards)
    next_card = scheduler.select_next_card()
    
    if not next_card:
        return jsonify({'error': 'No more cards available'}), 404
    
    # Get interval prediction for next card
    interval, _ = sample_next_review(next_card, user_obj)
    
    stats = {
        "next_interval": interval,
        "pomodoro_time": user_obj.pomodoro_length,
        "session_id": session_id
    }
    
    return jsonify({
        'success': True,
        'next_card': {**next_card.to_dict(), "stats": stats}
    })

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    user_name = request.args.get('user', 'default')
    deck_name = request.args.get('deck')
    
    # Get user
    user = User.query.filter_by(username=user_name).first()
    if not user:
        return jsonify([])
    
    # Get sessions
    query = Session.query.filter_by(user_id=user.id)
    
    # Filter by deck if provided
    if deck_name:
        deck = Deck.query.filter_by(name=deck_name).first()
        if deck:
            query = query.filter_by(deck_id=deck.id)
    
    # Filter out sessions that have been ended (deleted)
    query = query.filter(Session.end_time == None)
    
    sessions = query.all()
    return jsonify([session.to_dict() for session in sessions])

@app.route('/api/sessions', methods=['POST'])
def create_session():
    data = request.json
    deck_name = data.get('deck')
    user_name = data.get('user', 'default')
    session_name = data.get('name')
    
    if not deck_name:
        return jsonify({'error': 'Deck is required'}), 400
    
    # Get user
    user = User.query.filter_by(username=user_name).first()
    if not user:
        user = User(username=user_name)
        db.session.add(user)
    
    # Get deck
    deck = Deck.query.filter_by(name=deck_name).first()
    if not deck:
        return jsonify({'error': 'Deck not found'}), 404
    
    # Create session
    name = session_name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    session = Session(name=name, user_id=user.id, deck_id=deck.id)
    
    # Link session to user
    user.start_session(session.id)
    
    db.session.add(session)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'session': session.to_dict()
    })

@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(session.to_dict())

@app.route('/api/sessions/<session_id>/end', methods=['POST'])
def end_session(session_id):
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    session.end_session()
    
    # Update user profile
    user = session.user_profile
    if user:
        user.end_session()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'session': session.to_dict()
    })

@app.route('/api/stats/<stat_type>', methods=['GET'])
def get_stats(stat_type):
    user_name = request.args.get('user', 'default')
    deck_name = request.args.get('deck')
    session_id = request.args.get('session')
    
    # Get user
    user = User.query.filter_by(username=user_name).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Set global style for plots with dark background and light text
    plt.style.use('dark_background')
    plt.rcParams['figure.dpi'] = 100
    plt.rcParams['text.color'] = 'white'
    plt.rcParams['axes.labelcolor'] = 'white'
    plt.rcParams['axes.edgecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = '#2f2f31'
    plt.rcParams['axes.titlecolor'] = 'white'
    plt.rcParams['xtick.color'] = 'white'
    plt.rcParams['ytick.color'] = 'white'
    
    # Create figure with two subplots side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))
    fig.set_facecolor('#2f2f31')
    
    title_prefix = ""
    if stat_type == "user":
        title_prefix = f"User: {user_name}"
        data = user.get_recall_history()
    elif stat_type == "deck" and deck_name:
        title_prefix = f"Deck: {deck_name}"
        # Get the deck
        deck = Deck.query.filter_by(name=deck_name).first()
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
            
        # Get all reviews for cards in this deck
        data = []
        for card in deck.cards:
            for review in card.reviews:
                data.append((0, 1 if review.rating >= 7 else 0))
    elif stat_type == "session" and session_id:
        # Get the session
        session = Session.query.get(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        title_prefix = f"Session: {session.name}"
        data = [(0, 1 if review.rating >= 7 else 0) for review in session.reviews]
    else:
        return jsonify({'error': 'Invalid stat type or missing parameters'}), 400
    
    # Plot 1: Success rate - more compact with minimal elements
    if data:
        review_indices = list(range(1, len(data) + 1))
        cumulative_success = [sum(1 for _, s in data[:i+1] if s == 1) / (i+1) for i in range(len(data))]
        
        ax1.plot(review_indices, cumulative_success, '-', linewidth=2, color='#2496dc', label='Success')
        ax1.axhline(y=0.7, color='r', linestyle='--', linewidth=1, label='Target')
        ax1.set_xlabel('Review #', fontsize=9, color='white')
        ax1.set_ylabel('Rate', fontsize=9, color='white')
        ax1.set_title('Success Rate', fontsize=11, color='white', fontweight='bold')
        ax1.legend(fontsize=8, loc='lower right')
        ax1.grid(True, alpha=0.2)
        ax1.tick_params(axis='both', which='major', labelsize=8, colors='white')
        # Set y-axis limits to prevent extra white space
        ax1.set_ylim(0, 1.05)
        # Only show certain x ticks to avoid crowding
        if len(review_indices) > 10:
            step = len(review_indices) // 5
            ax1.set_xticks(review_indices[::step])
    
    # Plot 2: Performance distribution - more compact with minimal elements
    if data:
        successes = sum(s for _, s in data)
        failures = len(data) - successes
        alpha = 2 + successes  # Adding prior
        beta = 1 + failures    # Adding prior
        
        xs = np.linspace(0, 1, 100)  # Reduced number of points
        ys = [scipy.stats.beta.pdf(x, alpha, beta) for x in xs]
        
        ax2.plot(xs, ys, linewidth=1.5, color='#2496dc', label=f'α={alpha:.1f}, β={beta:.1f}')
        ax2.axvline(x=alpha/(alpha+beta), color='r', linestyle='--', linewidth=1, label='Mean')
        ax2.set_xlabel('Success Rate', fontsize=9, color='white')
        ax2.set_ylabel('Density', fontsize=9, color='white')
        ax2.set_title('Performance', fontsize=11, color='white', fontweight='bold')
        # Move legend outside the plot to save space
        ax2.legend(fontsize=8, loc='upper right')
        ax2.grid(True, alpha=0.2)
        ax2.tick_params(axis='both', which='major', labelsize=8, colors='white')
    
    # Remove excess whitespace around plots
    plt.tight_layout(pad=1.0)
    
    # Save plot to bytes - using the dark background color and higher quality
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#2f2f31', dpi=120)
    plt.close(fig)  # Close the figure to free up memory
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/cards/<deck>/<card_id>', methods=['DELETE'])
def delete_card(deck, card_id):
    # Find the deck
    deck_obj = Deck.query.filter_by(name=deck).first()
    if not deck_obj:
        return jsonify({'error': 'Deck not found'}), 404
        
    # Find the card
    card = Card.query.get(card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404
        
    # Remove card from deck
    try:
        # Remove from deck relationship
        deck_obj.cards.remove(card)
        # Delete any reviews associated with this card
        Review.query.filter_by(card_id=card.id).delete()
        # Delete the card itself
        db.session.delete(card)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting card: {str(e)}")
        return jsonify({'error': f'Failed to delete card: {str(e)}'}), 500

@app.route('/api/cards/<deck>/<card_id>', methods=['PUT'])
def update_card(deck, card_id):
    # Find the deck
    deck_obj = Deck.query.filter_by(name=deck).first()
    if not deck_obj:
        return jsonify({'error': 'Deck not found'}), 404
        
    # Find the card
    card = Card.query.get(card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404
        
    # Update card with new data
    try:
        data = request.json
        if 'front' in data:
            card.front = data['front']
        if 'back' in data:
            card.back = data['back']
        if 'frontImage' in data:
            card.front_image = data['frontImage']
        if 'backImage' in data:
            card.back_image = data['backImage']
        if 'type' in data:
            card.card_type = data['type']
            
        db.session.commit()
        return jsonify({'success': True, 'card': card.to_dict()})
    except Exception as e:
        db.session.rollback()
        print(f"Error updating card: {str(e)}")
        return jsonify({'error': f'Failed to update card: {str(e)}'}), 500

# ------------------- DB INITIALIZATION -------------------

# Note: We've removed db.create_all() to let migrations handle the database schema

if __name__ == '__main__':
    # Call create_default_user when the app starts
    create_default_user()
    app.run(port=5001, debug=True)
