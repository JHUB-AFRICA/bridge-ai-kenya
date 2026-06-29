# ================================================================
# BRIDGE-AI Kenya - Routes (JSON Version)
# ================================================================

import os
import json
import bleach  # ✅ NEW - For HTML sanitization
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for, 
    flash, session, jsonify, current_app, abort
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import login_manager
from app.extensions import User
from app.extensions import limiter  # ✅ NEW - Rate limiting
from app.services.json_service import JSONService
from app.services.audit_service import audit  # ✅ NEW - Audit logging

# Initialize JSON service
json_service = JSONService()


# ================================================================
# Helper Functions
# ================================================================

def slugify(text):
    if not text:
        return ''
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text


def sanitize_html(text):
    """Sanitize HTML content to prevent XSS."""
    if not text:
        return ''
    # Bleach allows safe HTML tags and attributes
    allowed_tags = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'blockquote',
        'code', 'pre', 'span', 'div'
    ]
    allowed_attrs = {
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title'],
        '*': ['class', 'id']
    }
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)


def get_upload_path(filename, subfolder=''):
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'app/static/images/uploads')
    if subfolder:
        path = os.path.join(upload_folder, subfolder)
    else:
        path = upload_folder
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, secure_filename(filename))


def safe_json_parse(value):
    if not value:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except:
            if ',' in value:
                return [item.strip() for item in value.split(',') if item.strip()]
            return [value] if value.strip() else None
    return None


def clean_dict(data):
    if not data:
        return data
    cleaned = {}
    for key, value in data.items():
        if value is not None and value != '':
            cleaned[key] = value
    return cleaned

# ================================================================
# Helper Functions - Add this after clean_dict()
# ================================================================

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, subfolder='activities'):
    """
    Save uploaded file and return the saved filename.
    File is saved to: app/static/uploads/{subfolder}/
    """
    if not file or not file.filename:
        return None
    
    if not allowed_file(file.filename):
        return None
    
    # Create upload folder if it doesn't exist
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', subfolder)
    os.makedirs(upload_folder, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    original_name = secure_filename(file.filename)
    filename = f"{timestamp}_{original_name}"
    
    # Save file
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    
    return filename
# ================================================================
# Public Blueprint
# ================================================================

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def index():
    activities = json_service.get_all('activities.json')
    events = json_service.get_all('events.json')
    settings = json_service.get_settings()
    
    published_activities = [a for a in activities if a.get('evidence_status') == 'published']
    latest_activities = sorted(published_activities, key=lambda x: x.get('date', ''), reverse=True)[:3]
    upcoming_events = [e for e in events if e.get('status') == 'upcoming'][:3]
    
    return render_template(
        'index.html',
        activities=latest_activities,
        events=upcoming_events,
        settings=settings
    )


@public_bp.route('/about/')
def about():
    return render_template('about.html')


@public_bp.route('/jkuat-role/')
def jkuat_role():
    team = json_service.get_all('team.json')
    visible_team = [t for t in team if t.get('is_visible') and t.get('consent_status') == 'approved']
    sorted_team = sorted(visible_team, key=lambda x: x.get('display_order', 0))
    return render_template('jkuat_role.html', team_members=sorted_team)


@public_bp.route('/smart-mushrooms/')
def smart_mushrooms():
    faqs = json_service.get_all('faqs.json')
    published_faqs = [f for f in faqs if f.get('is_published')]
    sorted_faqs = sorted(published_faqs, key=lambda x: x.get('display_order', 0))
    return render_template('smart_mushrooms.html', faqs=sorted_faqs)


@public_bp.route('/activities/')
def activities():
    all_activities = json_service.get_all('activities.json')
    published = [a for a in all_activities if a.get('evidence_status') == 'published']
    
    wp_filter = request.args.get('wp', '')
    audience_filter = request.args.get('audience', '')
    year_filter = request.args.get('year', '')
    
    if wp_filter:
        published = [a for a in published if a.get('wp_tag') == wp_filter]
    if audience_filter:
        published = [a for a in published if audience_filter.lower() in a.get('audience', '').lower()]
    if year_filter:
        published = [a for a in published if year_filter in a.get('date', '')]
    
    published = sorted(published, key=lambda x: x.get('date', ''), reverse=True)
    
    wp_options = list(set([a.get('wp_tag') for a in published if a.get('wp_tag')]))
    audience_options = list(set([a.get('audience') for a in published if a.get('audience')]))
    year_options = list(set([a.get('date', '')[:4] for a in published if a.get('date')]))
    
    return render_template(
        'activities.html',
        activities=published,
        wp_options=wp_options,
        audience_options=audience_options,
        year_options=year_options,
        current_wp=wp_filter,
        current_audience=audience_filter,
        current_year=year_filter
    )


@public_bp.route('/activities/<slug>/')
def activity_detail(slug):
    activities = json_service.get_all('activities.json')
    activity = None
    for a in activities:
        if a.get('slug') == slug and a.get('evidence_status') == 'published':
            activity = a
            break
    if not activity:
        abort(404)
    return render_template('activity_detail.html', activity=activity)


@public_bp.route('/training-and-wp5/')
def training_wp5():
    events = json_service.get_all('events.json')
    sorted_events = sorted(events, key=lambda x: x.get('date', ''))
    return render_template('training_wp5.html', events=sorted_events)


# ================================================================
# Public Routes - Training Events (List & Detail)
# ================================================================

@public_bp.route('/training-and-wp5/events/')
def training_events():
    """List all training events."""
    events = json_service.get_all('events.json')
    sorted_events = sorted(events, key=lambda x: x.get('date', ''))
    return render_template('training_events.html', events=sorted_events)


@public_bp.route('/training-and-wp5/events/<slug>/')
def event_detail(slug):
    """Dynamic event detail page for training events."""
    events = json_service.get_all('events.json')
    event = None
    for e in events:
        if e.get('slug') == slug:
            event = e
            break
    if not event:
        abort(404)
    return render_template('event_detail.html', event=event)
# ================================================================
# Public Routes - Training Materials
# ================================================================

@public_bp.route('/training-and-wp5/materials/')
def training_materials():
    """Training materials page with modules, videos, guides, and repositories."""
    materials = json_service.get_all('training-materials.json')
    
    # Sort modules by id
    sorted_materials = sorted(materials, key=lambda x: x.get('id', 0))
    
    # Get unique levels for filter
    levels = list(set([m.get('level', '') for m in sorted_materials if m.get('level')]))
    levels.sort()
    
    # Get unique tags for filter
    all_tags = []
    for m in sorted_materials:
        if m.get('tags'):
            all_tags.extend(m.get('tags', []))
    tags = list(set(all_tags))
    tags.sort()
    
    return render_template(
        'training_materials.html',
        materials=sorted_materials,
        levels=levels,
        tags=tags
    )


# ================================================================
# Public Routes - SME Mentoring
# ================================================================

@public_bp.route('/training-and-wp5/sme-mentoring/')
def sme_mentoring():
    """SME Mentoring page with challenges, hackathons, success stories, and interest form."""
    challenges = json_service.get_all('challenges.json')
    hackathons = json_service.get_all('hackathons.json')
    stories = json_service.get_all('success_stories.json')
    
    # Filter open challenges
    open_challenges = [c for c in challenges if c.get('status') == 'open']
    
    return render_template(
        'sme_mentoring.html',
        challenges=open_challenges,
        hackathons=hackathons,
        stories=stories
    )




# ================================================================
# Public Routes - Community of Practice
# ================================================================

@public_bp.route('/training-and-wp5/community-of-practice/')
def community_of_practice():
    """Community of Practice page with repositories, events, and join form."""
    repositories = json_service.get_all('repositories.json')
    events = json_service.get_all('community_events.json')
    return render_template(
        'community_of_practice.html',
        repositories=repositories,
        events=events
    )


# ================================================================
# Public Routes - Replication Toolkit
# ================================================================

@public_bp.route('/training-and-wp5/replication-toolkit/')
def replication_toolkit():
    """Replication Toolkit page with resources, templates, and lessons."""
    resources = json_service.get_all('replication_resources.json')
    templates = json_service.get_all('replication_templates.json')
    lessons = json_service.get_all('replication_lessons.json')
    return render_template(
        'replication_toolkit.html',
        resources=resources,
        templates=templates,
        lessons=lessons
    )




@public_bp.route('/resources/')
def resources():
    all_resources = json_service.get_all('resources.json')
    public_resources = [r for r in all_resources if r.get('is_public')]
    sorted_resources = sorted(public_resources, key=lambda x: x.get('created_at', ''), reverse=True)
    return render_template('resources.html', resources=sorted_resources)


@public_bp.route('/resources/<slug>/')
def resource_detail(slug):
    resources = json_service.get_all('resources.json')
    resource = None
    for r in resources:
        if r.get('slug') == slug and r.get('is_public'):
            resource = r
            break
    if not resource:
        abort(404)
    resource['download_count'] = resource.get('download_count', 0) + 1
    json_service.update('resources.json', resource['id'], resource)
    return render_template('resource_detail.html', resource=resource)


@public_bp.route('/partners/')
def partners():
    all_partners = json_service.get_all('partners.json')
    consortium_partners = [p for p in all_partners if p.get('is_consortium')]
    sorted_partners = sorted(consortium_partners, key=lambda x: x.get('display_order', 0))
    return render_template('partners.html', partners=sorted_partners)


@public_bp.route('/gallery/')
def gallery():
    all_albums = json_service.get_all('gallery.json')
    published_albums = [a for a in all_albums if a.get('is_published')]
    sorted_albums = sorted(published_albums, key=lambda x: x.get('date', ''), reverse=True)
    return render_template('gallery.html', albums=sorted_albums)


@public_bp.route('/gallery/<slug>/')
def gallery_album(slug):
    all_albums = json_service.get_all('gallery.json')
    album = None
    for a in all_albums:
        if a.get('slug') == slug and a.get('is_published'):
            album = a
            break
    if not album:
        abort(404)
    images = album.get('images', [])
    approved_images = [i for i in images if i.get('is_approved')]
    sorted_images = sorted(approved_images, key=lambda x: x.get('display_order', 0))
    return render_template('gallery_album.html', album=album, images=sorted_images)


@public_bp.route('/contact/', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        form_type = request.form.get('form_type', 'contact')
        
        if form_type == 'contact':
            name = request.form.get('name', '')
            email = request.form.get('email', '')
            organisation = request.form.get('organisation', '')
            audience = request.form.get('audience', '')
            message = request.form.get('message', '')
            
            if name and email and message:
                submission = {
                    'form_type': 'contact',
                    'data': {
                        'name': name,
                        'email': email,
                        'organisation': organisation,
                        'audience': audience,
                        'message': message
                    },
                    'ip_address': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'is_read': False,
                    'is_responded': False,
                    'submitted_at': datetime.now().isoformat()
                }
                json_service.create('submissions.json', submission)
                flash('Your message has been sent successfully. We will respond shortly.', 'success')
                return redirect(url_for('public.contact'))
            else:
                flash('Please fill in all required fields.', 'danger')
        
        elif form_type == 'training':
            name = request.form.get('name', '')
            email = request.form.get('email', '')
            phone = request.form.get('phone', '')
            county = request.form.get('county', '')
            audience = request.form.get('audience', '')
            training_interest = request.form.get('training_interest', '')
            
            if name and email:
                submission = {
                    'form_type': 'training',
                    'data': {
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'county': county,
                        'audience': audience,
                        'training_interest': training_interest
                    },
                    'ip_address': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'is_read': False,
                    'is_responded': False,
                    'submitted_at': datetime.now().isoformat()
                }
                json_service.create('submissions.json', submission)
                flash('Your training interest has been registered. We will contact you about upcoming opportunities.', 'success')
                return redirect(url_for('public.contact'))
            else:
                flash('Please fill in all required fields.', 'danger')
        
        elif form_type == 'media':
            name = request.form.get('name', '')
            email = request.form.get('email', '')
            outlet = request.form.get('outlet', '')
            request_type = request.form.get('request_type', '')
            deadline = request.form.get('deadline', '')
            message = request.form.get('message', '')
            
            if name and email and message:
                submission = {
                    'form_type': 'media',
                    'data': {
                        'name': name,
                        'email': email,
                        'outlet': outlet,
                        'request_type': request_type,
                        'deadline': deadline,
                        'message': message
                    },
                    'ip_address': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'is_read': False,
                    'is_responded': False,
                    'submitted_at': datetime.now().isoformat()
                }
                json_service.create('submissions.json', submission)
                flash('Your media request has been submitted. Our team will contact you shortly.', 'success')
                return redirect(url_for('public.contact'))
            else:
                flash('Please fill in all required fields.', 'danger')
    
    return render_template('contact.html')


@public_bp.route('/privacy-and-ethics/')
def privacy_ethics():
    return render_template('privacy_ethics.html')


# ================================================================
# Admin Blueprint
# ================================================================

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/login/', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # ✅ Rate limiting - 5 login attempts per minute
def admin_login():
    if current_user.is_authenticated:
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        users = json_service.get_all('users.json')
        user = None
        for u in users:
            if u.get('username') == username:
                user = u
                break
        
        if user and check_password_hash(user.get('password_hash', ''), password):
            user_obj = User(user)
            login_user(user_obj, remember=True)
            session.permanent = True
            
            user['last_login'] = datetime.now().isoformat()
            json_service.update('users.json', user['id'], user)
            
            # ✅ Audit log
            audit.log_action(
                user=username,
                action='LOGIN_SUCCESS',
                details={'ip': request.remote_addr}
            )
            
            flash('Welcome back!', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('admin.admin_dashboard'))
        else:
            # ✅ Audit log for failed login
            audit.log_action(
                user=username,
                action='LOGIN_FAILED',
                details={'ip': request.remote_addr}
            )
            flash('Invalid username or password.', 'danger')
    
    return render_template('admin/login.html')


@admin_bp.route('/logout/')
@login_required
def admin_logout():
    # ✅ Audit log
    audit.log_action(
        user=current_user.username,
        action='LOGOUT',
        details={'ip': request.remote_addr}
    )
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin.admin_login'))


@admin_bp.route('/')
@login_required
def admin_dashboard():
    stats = {
        'activities': len(json_service.get_all('activities.json')),
        'published_activities': len([a for a in json_service.get_all('activities.json') if a.get('evidence_status') == 'published']),
        'events': len(json_service.get_all('events.json')),
        'upcoming_events': len([e for e in json_service.get_all('events.json') if e.get('status') == 'upcoming']),
        'resources': len(json_service.get_all('resources.json')),
        'partners': len(json_service.get_all('partners.json')),
        'team': len(json_service.get_all('team.json')),
        'albums': len(json_service.get_all('gallery.json')),
        'faqs': len(json_service.get_all('faqs.json')),
        'submissions': len(json_service.get_all('submissions.json')),
        'unread_submissions': len([s for s in json_service.get_all('submissions.json') if not s.get('is_read')]),
        
        'training_materials': len(json_service.get_all('training-materials.json')),
        'challenges': len(json_service.get_all('challenges.json')),
        'hackathons': len(json_service.get_all('hackathons.json')),
        'stories': len(json_service.get_all('success_stories.json')),
        'sme_submissions': len(json_service.get_all('sme_submissions.json')),
        'repositories': len(json_service.get_all('repositories.json')),
        'community_events': len(json_service.get_all('community_events.json')),
        'community_submissions': len(json_service.get_all('community_submissions.json')),
        'replication_resources': len(json_service.get_all('replication_resources.json')),
        'replication_templates': len(json_service.get_all('replication_templates.json')),
        'replication_lessons': len(json_service.get_all('replication_lessons.json')),



    }
    return render_template('admin/dashboard.html', stats=stats)


@admin_bp.route('/activities/')
@login_required
def admin_activities():
    return render_template('admin/activities.html')


@admin_bp.route('/events/')
@login_required
def admin_events():
    return render_template('admin/events.html')


@admin_bp.route('/resources/')
@login_required
def admin_resources():
    return render_template('admin/resources.html')


@admin_bp.route('/partners/')
@login_required
def admin_partners():
    return render_template('admin/partners.html')


@admin_bp.route('/team/')
@login_required
def admin_team():
    return render_template('admin/team.html')


@admin_bp.route('/gallery/')
@login_required
def admin_gallery():
    return render_template('admin/gallery.html')


@admin_bp.route('/faqs/')
@login_required
def admin_faqs():
    return render_template('admin/faqs.html')


@admin_bp.route('/training-materials/')
@login_required
def admin_training_materials():
    return render_template('admin/training_materials.html')



@admin_bp.route('/sme/')
@login_required
def admin_sme():
    """Admin page for SME management: challenges, hackathons, stories, submissions."""
    return render_template('admin/sme.html')



@admin_bp.route('/community/')
@login_required
def admin_community():
    """Admin page for Community management: repositories, events, submissions."""
    return render_template('admin/community.html')



@admin_bp.route('/replication/')
@login_required
def admin_replication():
    """Admin page for Replication Toolkit management."""
    return render_template('admin/replication.html')




@admin_bp.route('/submissions/')
@login_required
def admin_submissions():
    return render_template('admin/submissions.html')


@admin_bp.route('/test-session/')
@login_required
def admin_test_session():
    return jsonify({
        'is_authenticated': current_user.is_authenticated,
        'user_id': current_user.get_id() if current_user.is_authenticated else None,
        'username': current_user.username if current_user.is_authenticated else None,
        'session_keys': list(session.keys()),
        'session_data': {k: str(v) for k, v in session.items()},
        'session_permanent': session.permanent
    })


# ================================================================
# API Blueprint
# ================================================================

api_bp = Blueprint('api', __name__, url_prefix='/api')


def api_login_required():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401
    return None


# ================================================================
# API - Hero Images
# ================================================================

@api_bp.route('/hero-images/', methods=['GET'])
def api_get_hero_images():
    hero_folder = os.path.join(current_app.root_path, 'static', 'images', 'hero')
    images = []
    if os.path.exists(hero_folder):
        for file in os.listdir(hero_folder):
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                images.append(file)
    images.sort()
    return jsonify({'images': images})


# ================================================================
# API - Activities (FormData + Image Upload Support)
# ================================================================

@api_bp.route('/activities/', methods=['GET'])
# ✅ REMOVED auth check - Public pages need this!
def api_get_activities():
    try:
        activities = json_service.get_all('activities.json')
        return jsonify(activities)
    except Exception as e:
        print(f"❌ Error getting activities: {e}")
        return jsonify([])




@api_bp.route('/activities/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_activity():
    try:
        # ============================================================
        # CHECK IF REQUEST IS FORM DATA (with image) OR JSON
        # ============================================================
        is_form_data = request.content_type and 'multipart/form-data' in request.content_type
        
        if is_form_data:
            # ============================================================
            # ✅ HANDLE FORM DATA WITH IMAGE UPLOAD
            # ============================================================
            
            # Get fields from request.form
            title = request.form.get('title', '').strip()
            body = request.form.get('body', '').strip()
            slug = request.form.get('slug', '').strip()
            summary = request.form.get('summary', '').strip()
            date = request.form.get('date', '').strip()
            location = request.form.get('location', '').strip()
            wp_tag = request.form.get('wp_tag', '').strip()
            activity_type = request.form.get('activity_type', '').strip()
            audience = request.form.get('audience', '').strip()
            author = request.form.get('author', '').strip()
            evidence_status = request.form.get('evidence_status', 'draft').strip()
            
            # Validate required fields
            if not title:
                return jsonify({'success': False, 'error': 'Title is required'}), 400
            if not body:
                return jsonify({'success': False, 'error': 'Body is required'}), 400
            
            # Sanitize inputs
            title = sanitize_html(title)
            body = sanitize_html(body)
            if summary:
                summary = sanitize_html(summary)
            if location:
                location = sanitize_html(location)
            if author:
                author = sanitize_html(author)
            
            # Auto-generate slug if not provided
            if not slug:
                slug = slugify(title)
                if not slug:
                    slug = f"activity-{int(datetime.now().timestamp())}"
            
            # Set date if not provided
            if not date:
                date = datetime.now().strftime('%Y-%m-%d')
            
            # ============================================================
            # ✅ HANDLE IMAGE UPLOAD
            # ============================================================
            featured_image = None
            if 'featured_image' in request.files:
                file = request.files['featured_image']
                if file and file.filename:
                    filename = save_uploaded_file(file, 'activities')
                    if filename:
                        featured_image = f"uploads/activities/{filename}"
            
            # Build activity data
            activity_data = {
                'title': title,
                'slug': slug,
                'body': body,
                'date': date,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'evidence_status': evidence_status
            }
            
            # Add optional fields if they have values
            if summary:
                activity_data['summary'] = summary
            if location:
                activity_data['location'] = location
            if wp_tag:
                activity_data['wp_tag'] = wp_tag
            if activity_type:
                activity_data['activity_type'] = activity_type
            if audience:
                activity_data['audience'] = audience
            if author:
                activity_data['author'] = author
            if featured_image:
                activity_data['featured_image'] = featured_image
            
            print(f"📝 FormData - Activity data to save: {activity_data}")
            
            # Save to JSON
            result = json_service.create('activities.json', activity_data)
            
            # Audit log
            audit.log_action(
                user=current_user.username,
                action='CREATE_ACTIVITY',
                details={'title': title, 'wp_tag': wp_tag, 'has_image': bool(featured_image)}
            )
            
            if result:
                return jsonify({
                    'success': True,
                    'data': result,
                    'message': 'Activity created successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to save activity to JSON'
                }), 500
        
        else:
            # ============================================================
            # ✅ HANDLE JSON (No image upload - for other admin pages)
            # ============================================================
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
            
            # Sanitize input
            title = data.get('title', '').strip()
            title = sanitize_html(title)
            if not title:
                return jsonify({'success': False, 'error': 'Title is required'}), 400
            
            body = data.get('body', '').strip()
            body = sanitize_html(body)
            if not body:
                return jsonify({'success': False, 'error': 'Body is required'}), 400
            
            slug = data.get('slug', '').strip()
            if not slug:
                slug = slugify(title)
                if not slug:
                    slug = f"activity-{int(datetime.now().timestamp())}"
            
            date = data.get('date', '')
            if not date:
                date = datetime.now().isoformat()
            
            # Sanitize optional fields
            summary = data.get('summary', '').strip()
            summary = sanitize_html(summary) if summary else ''
            location = data.get('location', '').strip()
            location = sanitize_html(location) if location else ''
            author = data.get('author', '').strip()
            author = sanitize_html(author) if author else ''
            
            gallery = safe_json_parse(data.get('gallery'))
            related_resources = safe_json_parse(data.get('related_resources'))
            evidence_status = data.get('evidence_status', 'draft')
            
            activity_data = {
                'title': title,
                'slug': slug,
                'body': body,
                'date': date,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'evidence_status': evidence_status
            }
            
            if summary:
                activity_data['summary'] = summary
            if location:
                activity_data['location'] = location
            if data.get('wp_tag'):
                activity_data['wp_tag'] = data['wp_tag']
            if data.get('activity_type'):
                activity_data['activity_type'] = data['activity_type']
            if data.get('audience'):
                activity_data['audience'] = data['audience']
            if author:
                activity_data['author'] = author
            if data.get('featured_image'):
                activity_data['featured_image'] = data['featured_image'].strip()
            if gallery:
                activity_data['gallery'] = gallery
            if related_resources:
                activity_data['related_resources'] = related_resources
            
            print(f"📝 JSON - Activity data to save: {activity_data}")
            
            result = json_service.create('activities.json', activity_data)
            
            audit.log_action(
                user=current_user.username,
                action='CREATE_ACTIVITY',
                details={'title': title, 'wp_tag': data.get('wp_tag')}
            )
            
            if result:
                return jsonify({
                    'success': True,
                    'data': result,
                    'message': 'Activity created successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to save activity to JSON'
                }), 500
        
    except Exception as e:
        audit.log_action(
            user=current_user.username if current_user.is_authenticated else 'Unknown',
            action='CREATE_ACTIVITY_ERROR',
            details={'error': str(e)}
        )
        print(f"❌ Error creating activity: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@api_bp.route('/activities/<int:id>', methods=['GET'])
@login_required
def api_get_activity(id):
    activity = json_service.get_by_id('activities.json', id)
    if not activity:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(activity)


@api_bp.route('/activities/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_activity(id):
    try:
        # Get existing activity first
        existing = json_service.get_by_id('activities.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        # ============================================================
        # CHECK IF REQUEST IS FORM DATA (with image) OR JSON
        # ============================================================
        is_form_data = request.content_type and 'multipart/form-data' in request.content_type
        
        if is_form_data:
            # ============================================================
            # ✅ HANDLE FORM DATA WITH IMAGE UPLOAD
            # ============================================================
            
            # Get fields from request.form
            title = request.form.get('title', '').strip()
            body = request.form.get('body', '').strip()
            slug = request.form.get('slug', '').strip()
            summary = request.form.get('summary', '').strip()
            date = request.form.get('date', '').strip()
            location = request.form.get('location', '').strip()
            wp_tag = request.form.get('wp_tag', '').strip()
            activity_type = request.form.get('activity_type', '').strip()
            audience = request.form.get('audience', '').strip()
            author = request.form.get('author', '').strip()
            evidence_status = request.form.get('evidence_status', 'draft').strip()
            
            # Validate required fields
            if not title:
                return jsonify({'success': False, 'error': 'Title is required'}), 400
            
            # Sanitize inputs
            title = sanitize_html(title)
            if body:
                body = sanitize_html(body)
            if summary:
                summary = sanitize_html(summary)
            if location:
                location = sanitize_html(location)
            if author:
                author = sanitize_html(author)
            
            # Auto-generate slug if not provided
            if not slug:
                slug = slugify(title)
                if not slug:
                    slug = f"activity-{int(datetime.now().timestamp())}"
            
            # Set date if not provided
            if not date:
                date = datetime.now().strftime('%Y-%m-%d')
            
            # ============================================================
            # ✅ HANDLE IMAGE UPLOAD (replaces old image)
            # ============================================================
            featured_image = existing.get('featured_image')  # Keep existing by default
            
            if 'featured_image' in request.files:
                file = request.files['featured_image']
                if file and file.filename:
                    # Delete old image if exists
                    if existing.get('featured_image'):
                        old_path = os.path.join(
                            current_app.root_path, 
                            'static', 
                            existing['featured_image']
                        )
                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                                print(f"🗑️ Deleted old image: {old_path}")
                            except Exception as e:
                                print(f"⚠️ Could not delete old image: {e}")
                    
                    # Save new image
                    filename = save_uploaded_file(file, 'activities')
                    if filename:
                        featured_image = f"uploads/activities/{filename}"
            
            # Build updated data
            updated_data = {
                'title': title,
                'body': body,
                'slug': slug,
                'date': date,
                'updated_at': datetime.now().isoformat(),
                'evidence_status': evidence_status
            }
            
            # Add optional fields if they have values
            if summary:
                updated_data['summary'] = summary
            if location:
                updated_data['location'] = location
            if wp_tag:
                updated_data['wp_tag'] = wp_tag
            if activity_type:
                updated_data['activity_type'] = activity_type
            if audience:
                updated_data['audience'] = audience
            if author:
                updated_data['author'] = author
            if featured_image:
                updated_data['featured_image'] = featured_image
            
            # Keep created_at from existing
            updated_data['created_at'] = existing.get('created_at', datetime.now().isoformat())
            
            print(f"📝 FormData - Updated activity data: {updated_data}")
            
            result = json_service.update('activities.json', id, updated_data)
            
            audit.log_action(
                user=current_user.username,
                action='UPDATE_ACTIVITY',
                details={'id': id, 'title': title, 'has_image': bool(featured_image)}
            )
            
            if not result:
                return jsonify({'error': 'Not found'}), 404
            
            return jsonify({'success': True, 'data': result, 'message': 'Activity updated successfully'})
        
        else:
            # ============================================================
            # ✅ HANDLE JSON (No image upload)
            # ============================================================
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
            
            # Sanitize input
            title = data.get('title', '').strip()
            title = sanitize_html(title)
            if not title:
                return jsonify({'success': False, 'error': 'Title is required'}), 400
            
            body = data.get('body', '').strip()
            body = sanitize_html(body) if body else existing.get('body', '')
            
            slug = data.get('slug', '').strip() or slugify(title)
            date = data.get('date', datetime.now().isoformat())
            evidence_status = data.get('evidence_status', 'draft')
            
            updated_data = {
                'title': title,
                'body': body,
                'slug': slug,
                'date': date,
                'updated_at': datetime.now().isoformat(),
                'evidence_status': evidence_status
            }
            
            # Sanitize optional fields
            if data.get('summary'):
                updated_data['summary'] = sanitize_html(data['summary'].strip())
            if data.get('location'):
                updated_data['location'] = sanitize_html(data['location'].strip())
            if data.get('wp_tag'):
                updated_data['wp_tag'] = data['wp_tag']
            if data.get('activity_type'):
                updated_data['activity_type'] = data['activity_type']
            if data.get('audience'):
                updated_data['audience'] = data['audience']
            if data.get('author'):
                updated_data['author'] = sanitize_html(data['author'].strip())
            if data.get('featured_image'):
                updated_data['featured_image'] = data['featured_image'].strip()
            if data.get('gallery'):
                gallery = safe_json_parse(data['gallery'])
                if gallery:
                    updated_data['gallery'] = gallery
            if data.get('related_resources'):
                related = safe_json_parse(data['related_resources'])
                if related:
                    updated_data['related_resources'] = related
            
            # Keep created_at from existing
            updated_data['created_at'] = existing.get('created_at', datetime.now().isoformat())
            
            result = json_service.update('activities.json', id, updated_data)
            
            audit.log_action(
                user=current_user.username,
                action='UPDATE_ACTIVITY',
                details={'id': id, 'title': title}
            )
            
            if not result:
                return jsonify({'error': 'Not found'}), 404
            
            return jsonify({'success': True, 'data': result, 'message': 'Activity updated successfully'})
        
    except Exception as e:
        audit.log_action(
            user=current_user.username if current_user.is_authenticated else 'Unknown',
            action='UPDATE_ACTIVITY_ERROR',
            details={'id': id, 'error': str(e)}
        )
        print(f"❌ Error updating activity: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/activities/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_activity(id):
    try:
        # Get activity for logging and image cleanup
        activity = json_service.get_by_id('activities.json', id)
        if activity:
            # Delete featured image if exists
            if activity.get('featured_image'):
                image_path = os.path.join(
                    current_app.root_path, 
                    'static', 
                    activity['featured_image']
                )
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                        print(f"🗑️ Deleted image: {image_path}")
                    except Exception as e:
                        print(f"⚠️ Could not delete image: {e}")
            
            audit.log_action(
                user=current_user.username,
                action='DELETE_ACTIVITY',
                details={'id': id, 'title': activity.get('title')}
            )
        
        result = json_service.delete('activities.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Activity deleted successfully'})
    except Exception as e:
        audit.log_action(
            user=current_user.username if current_user.is_authenticated else 'Unknown',
            action='DELETE_ACTIVITY_ERROR',
            details={'id': id, 'error': str(e)}
        )
        return jsonify({'success': False, 'error': str(e)}), 400

# ================================================================
# API - Events
# ================================================================

@api_bp.route('/events/', methods=['GET'])
def api_get_events():
    events = json_service.get_all('events.json')
    return jsonify(events)


@api_bp.route('/events/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_event():
    data = request.get_json()
    try:
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        # ✅ Sanitize
        title = sanitize_html(data.get('title', '').strip())
        data['title'] = title
        
        if not data.get('slug'):
            data['slug'] = slugify(title)
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.create('events.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_EVENT',
            details={'title': title}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Event created successfully'})
    except Exception as e:
        audit.log_action(
            user=current_user.username if current_user.is_authenticated else 'Unknown',
            action='CREATE_EVENT_ERROR',
            details={'error': str(e)}
        )
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/events/<int:id>', methods=['GET'])
@login_required
def api_get_event(id):
    event = json_service.get_by_id('events.json', id)
    if not event:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(event)


@api_bp.route('/events/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_event(id):
    data = request.get_json()
    try:
        # ✅ Sanitize
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.update('events.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_EVENT',
            details={'id': id, 'title': data.get('title')}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Event updated successfully'})
    except Exception as e:
        audit.log_action(
            user=current_user.username if current_user.is_authenticated else 'Unknown',
            action='UPDATE_EVENT_ERROR',
            details={'id': id, 'error': str(e)}
        )
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/events/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_event(id):
    try:
        event = json_service.get_by_id('events.json', id)
        if event:
            audit.log_action(
                user=current_user.username,
                action='DELETE_EVENT',
                details={'id': id, 'title': event.get('title')}
            )
        result = json_service.delete('events.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Event deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Resources
# ================================================================

@api_bp.route('/resources/', methods=['GET'])
@login_required
def api_get_resources():
    resources = json_service.get_all('resources.json')
    return jsonify(resources)


@api_bp.route('/resources/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_resource():
    data = request.get_json()
    try:
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        title = sanitize_html(data.get('title', '').strip())
        data['title'] = title
        
        if not data.get('slug'):
            data['slug'] = slugify(title)
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.create('resources.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_RESOURCE',
            details={'title': title}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Resource created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/resources/<int:id>', methods=['GET'])
@login_required
def api_get_resource(id):
    resource = json_service.get_by_id('resources.json', id)
    if not resource:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(resource)


@api_bp.route('/resources/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_resource(id):
    data = request.get_json()
    try:
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.update('resources.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_RESOURCE',
            details={'id': id, 'title': data.get('title')}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Resource updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/resources/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_resource(id):
    try:
        resource = json_service.get_by_id('resources.json', id)
        if resource:
            audit.log_action(
                user=current_user.username,
                action='DELETE_RESOURCE',
                details={'id': id, 'title': resource.get('title')}
            )
        result = json_service.delete('resources.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Resource deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Partners
# ================================================================

@api_bp.route('/partners/', methods=['GET'])
@login_required
def api_get_partners():
    partners = json_service.get_all('partners.json')
    return jsonify(partners)


@api_bp.route('/partners/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_partner():
    data = request.get_json()
    try:
        if not data.get('name') or not data.get('short_name') or not data.get('country'):
            return jsonify({'success': False, 'error': 'Name, Short Name, and Country are required'}), 400
        
        data['name'] = sanitize_html(data['name'].strip())
        data['short_name'] = sanitize_html(data['short_name'].strip())
        data['country'] = sanitize_html(data['country'].strip())
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.create('partners.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_PARTNER',
            details={'name': data['name']}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Partner created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/partners/<int:id>', methods=['GET'])
@login_required
def api_get_partner(id):
    partner = json_service.get_by_id('partners.json', id)
    if not partner:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(partner)


@api_bp.route('/partners/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_partner(id):
    data = request.get_json()
    try:
        if data.get('name'):
            data['name'] = sanitize_html(data['name'].strip())
        if data.get('short_name'):
            data['short_name'] = sanitize_html(data['short_name'].strip())
        if data.get('country'):
            data['country'] = sanitize_html(data['country'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.update('partners.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_PARTNER',
            details={'id': id, 'name': data.get('name')}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Partner updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/partners/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_partner(id):
    try:
        partner = json_service.get_by_id('partners.json', id)
        if partner:
            audit.log_action(
                user=current_user.username,
                action='DELETE_PARTNER',
                details={'id': id, 'name': partner.get('name')}
            )
        result = json_service.delete('partners.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Partner deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Team Members
# ================================================================

@api_bp.route('/team/', methods=['GET'])
@login_required
def api_get_team():
    team = json_service.get_all('team.json')
    return jsonify(team)


@api_bp.route('/team/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_team():
    data = request.get_json()
    try:
        if not data.get('name') or not data.get('role'):
            return jsonify({'success': False, 'error': 'Name and Role are required'}), 400
        
        data['name'] = sanitize_html(data['name'].strip())
        data['role'] = sanitize_html(data['role'].strip())
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.create('team.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_TEAM_MEMBER',
            details={'name': data['name']}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Team member created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/team/<int:id>', methods=['GET'])
@login_required
def api_get_team_member(id):
    member = json_service.get_by_id('team.json', id)
    if not member:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(member)


@api_bp.route('/team/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_team(id):
    data = request.get_json()
    try:
        if data.get('name'):
            data['name'] = sanitize_html(data['name'].strip())
        if data.get('role'):
            data['role'] = sanitize_html(data['role'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.update('team.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_TEAM_MEMBER',
            details={'id': id, 'name': data.get('name')}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Team member updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/team/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_team(id):
    try:
        member = json_service.get_by_id('team.json', id)
        if member:
            audit.log_action(
                user=current_user.username,
                action='DELETE_TEAM_MEMBER',
                details={'id': id, 'name': member.get('name')}
            )
        result = json_service.delete('team.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Team member deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - FAQs
# ================================================================

@api_bp.route('/faqs/', methods=['GET'])
@login_required
def api_get_faqs():
    faqs = json_service.get_all('faqs.json')
    return jsonify(faqs)


@api_bp.route('/faqs/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_faq():
    data = request.get_json()
    try:
        if not data.get('question') or not data.get('answer'):
            return jsonify({'success': False, 'error': 'Question and Answer are required'}), 400
        
        data['question'] = sanitize_html(data['question'].strip())
        data['answer'] = sanitize_html(data['answer'].strip())
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.create('faqs.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_FAQ',
            details={'question': data['question']}
        )
        return jsonify({'success': True, 'data': result, 'message': 'FAQ created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/faqs/<int:id>', methods=['GET'])
@login_required
def api_get_faq(id):
    faq = json_service.get_by_id('faqs.json', id)
    if not faq:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(faq)


@api_bp.route('/faqs/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_faq(id):
    data = request.get_json()
    try:
        if data.get('question'):
            data['question'] = sanitize_html(data['question'].strip())
        if data.get('answer'):
            data['answer'] = sanitize_html(data['answer'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.update('faqs.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_FAQ',
            details={'id': id, 'question': data.get('question')}
        )
        return jsonify({'success': True, 'data': result, 'message': 'FAQ updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/faqs/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_faq(id):
    try:
        faq = json_service.get_by_id('faqs.json', id)
        if faq:
            audit.log_action(
                user=current_user.username,
                action='DELETE_FAQ',
                details={'id': id, 'question': faq.get('question')}
            )
        result = json_service.delete('faqs.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'FAQ deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Gallery Albums
# ================================================================

@api_bp.route('/gallery/', methods=['GET'])
@login_required
def api_get_gallery():
    albums = json_service.get_all('gallery.json')
    return jsonify(albums)


@api_bp.route('/gallery/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_gallery():
    data = request.get_json()
    try:
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Album title is required'}), 400
        
        data['title'] = sanitize_html(data['title'].strip())
        if not data.get('slug'):
            data['slug'] = slugify(data['title'])
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.create('gallery.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_GALLERY_ALBUM',
            details={'title': data['title']}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Album created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/gallery/<int:id>', methods=['GET'])
@login_required
def api_get_gallery_album(id):
    album = json_service.get_by_id('gallery.json', id)
    if not album:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(album)


@api_bp.route('/gallery/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_gallery_album(id):
    data = request.get_json()
    try:
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        data['updated_at'] = datetime.now().isoformat()
        result = json_service.update('gallery.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_GALLERY_ALBUM',
            details={'id': id, 'title': data.get('title')}
        )
        return jsonify({'success': True, 'data': result, 'message': 'Album updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/gallery/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_gallery_album(id):
    try:
        album = json_service.get_by_id('gallery.json', id)
        if album:
            audit.log_action(
                user=current_user.username,
                action='DELETE_GALLERY_ALBUM',
                details={'id': id, 'title': album.get('title')}
            )
        result = json_service.delete('gallery.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Album deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Gallery Images
# ================================================================

@api_bp.route('/gallery/<int:album_id>/images/', methods=['GET'])
@login_required
def api_get_gallery_images(album_id):
    album = json_service.get_by_id('gallery.json', album_id)
    if not album:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(album.get('images', []))


@api_bp.route('/gallery/images/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_gallery_image():
    data = request.get_json()
    try:
        album_id = data.get('album_id')
        album = json_service.get_by_id('gallery.json', album_id)
        if not album:
            return jsonify({'error': 'Album not found'}), 404
        
        images = album.get('images', [])
        max_id = max([img.get('id', 0) for img in images]) if images else 0
        data['id'] = max_id + 1
        
        if data.get('caption'):
            data['caption'] = sanitize_html(data['caption'].strip())
        
        images.append(data)
        album['images'] = images
        album['updated_at'] = datetime.now().isoformat()
        json_service.update('gallery.json', album_id, album)
        
        audit.log_action(
            user=current_user.username,
            action='ADD_GALLERY_IMAGE',
            details={'album_id': album_id, 'caption': data.get('caption')}
        )
        return jsonify({'success': True, 'data': data, 'message': 'Image added successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/gallery/images/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_gallery_image(id):
    try:
        albums = json_service.get_all('gallery.json')
        data = request.get_json()
        
        if data.get('caption'):
            data['caption'] = sanitize_html(data['caption'].strip())
        
        for album in albums:
            images = album.get('images', [])
            for i, img in enumerate(images):
                if img.get('id') == id:
                    images[i] = {**img, **data}
                    album['images'] = images
                    album['updated_at'] = datetime.now().isoformat()
                    json_service.update('gallery.json', album['id'], album)
                    
                    audit.log_action(
                        user=current_user.username,
                        action='UPDATE_GALLERY_IMAGE',
                        details={'id': id, 'caption': data.get('caption')}
                    )
                    return jsonify({'success': True, 'message': 'Image updated successfully'})
        
        return jsonify({'error': 'Image not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/gallery/images/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_gallery_image(id):
    try:
        albums = json_service.get_all('gallery.json')
        
        for album in albums:
            images = album.get('images', [])
            for i, img in enumerate(images):
                if img.get('id') == id:
                    del images[i]
                    album['images'] = images
                    album['updated_at'] = datetime.now().isoformat()
                    json_service.update('gallery.json', album['id'], album)
                    
                    audit.log_action(
                        user=current_user.username,
                        action='DELETE_GALLERY_IMAGE',
                        details={'id': id}
                    )
                    return jsonify({'success': True, 'message': 'Image deleted successfully'})
        
        return jsonify({'error': 'Image not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400




# ================================================================
# API - Training Materials
# ================================================================

@api_bp.route('/training-materials/', methods=['GET'])
# ✅ REMOVED @login_required - Public pages need this!
def api_get_training_materials():
    """Get all training materials."""
    try:
        materials = json_service.get_all('training-materials.json')
        return jsonify(materials)
    except Exception as e:
        print(f"❌ Error getting training materials: {e}")
        return jsonify([])


@api_bp.route('/training-materials/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_training_material():
    """Create a new training material."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        # Sanitize
        title = sanitize_html(data.get('title', '').strip())
        data['title'] = title
        
        if not data.get('slug'):
            data['slug'] = slugify(title)
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('training-materials.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_TRAINING_MATERIAL',
            details={'title': title}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Training material created successfully'})
    except Exception as e:
        audit.log_action(
            user=current_user.username if current_user.is_authenticated else 'Unknown',
            action='CREATE_TRAINING_MATERIAL_ERROR',
            details={'error': str(e)}
        )
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/training-materials/<int:id>', methods=['GET'])
@login_required
def api_get_training_material(id):
    """Get a single training material by ID."""
    material = json_service.get_by_id('training-materials.json', id)
    if not material:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(material)


@api_bp.route('/training-materials/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_training_material(id):
    """Update a training material."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('training-materials.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        # Sanitize
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('training-materials.json', id, data)
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_TRAINING_MATERIAL',
            details={'id': id, 'title': data.get('title')}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Training material updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/training-materials/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_training_material(id):
    """Delete a training material."""
    try:
        material = json_service.get_by_id('training-materials.json', id)
        if material:
            audit.log_action(
                user=current_user.username,
                action='DELETE_TRAINING_MATERIAL',
                details={'id': id, 'title': material.get('title')}
            )
        
        result = json_service.delete('training-materials.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Training material deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Submissions
# ================================================================

@api_bp.route('/submissions/', methods=['GET'])
@login_required
def api_get_submissions():
    submissions = json_service.get_all('submissions.json')
    sorted_submissions = sorted(submissions, key=lambda x: x.get('submitted_at', ''), reverse=True)
    return jsonify(sorted_submissions)


@api_bp.route('/submissions/<int:id>/', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_submission(id):
    data = request.get_json()
    try:
        result = json_service.update('submissions.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_SUBMISSION',
            details={'id': id, 'is_read': data.get('is_read')}
        )
        return jsonify({'success': True, 'message': 'Submission updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/submissions/<int:id>/', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_submission(id):
    try:
        submission = json_service.get_by_id('submissions.json', id)
        if submission:
            audit.log_action(
                user=current_user.username,
                action='DELETE_SUBMISSION',
                details={'id': id}
            )
        result = json_service.delete('submissions.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Submission deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400



# ================================================================
# API - SME Challenges
# ================================================================

@api_bp.route('/challenges/', methods=['GET'])
@login_required
def api_get_challenges():
    """Get all challenges."""
    try:
        challenges = json_service.get_all('challenges.json')
        return jsonify(challenges)
    except Exception as e:
        print(f"❌ Error getting challenges: {e}")
        return jsonify([])


@api_bp.route('/challenges/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_challenge():
    """Create a new challenge."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        # Sanitize
        title = sanitize_html(data.get('title', '').strip())
        data['title'] = title
        
        if not data.get('slug'):
            data['slug'] = slugify(title)
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('challenges.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_CHALLENGE',
            details={'title': title}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Challenge created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/challenges/<int:id>', methods=['GET'])
@login_required
def api_get_challenge(id):
    """Get a single challenge by ID."""
    challenge = json_service.get_by_id('challenges.json', id)
    if not challenge:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(challenge)


@api_bp.route('/challenges/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_challenge(id):
    """Update a challenge."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('challenges.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('challenges.json', id, data)
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_CHALLENGE',
            details={'id': id, 'title': data.get('title')}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Challenge updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/challenges/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_challenge(id):
    """Delete a challenge."""
    try:
        challenge = json_service.get_by_id('challenges.json', id)
        if challenge:
            audit.log_action(
                user=current_user.username,
                action='DELETE_CHALLENGE',
                details={'id': id, 'title': challenge.get('title')}
            )
        
        result = json_service.delete('challenges.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Challenge deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - SME Hackathons
# ================================================================

@api_bp.route('/hackathons/', methods=['GET'])
@login_required
def api_get_hackathons():
    """Get all hackathons."""
    try:
        hackathons = json_service.get_all('hackathons.json')
        return jsonify(hackathons)
    except Exception as e:
        print(f"❌ Error getting hackathons: {e}")
        return jsonify([])


@api_bp.route('/hackathons/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_hackathon():
    """Create a new hackathon."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        title = sanitize_html(data.get('title', '').strip())
        data['title'] = title
        
        if not data.get('slug'):
            data['slug'] = slugify(title)
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('hackathons.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_HACKATHON',
            details={'title': title}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Hackathon created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/hackathons/<int:id>', methods=['GET'])
@login_required
def api_get_hackathon(id):
    """Get a single hackathon by ID."""
    hackathon = json_service.get_by_id('hackathons.json', id)
    if not hackathon:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(hackathon)


@api_bp.route('/hackathons/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_hackathon(id):
    """Update a hackathon."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('hackathons.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('hackathons.json', id, data)
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_HACKATHON',
            details={'id': id, 'title': data.get('title')}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Hackathon updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/hackathons/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_hackathon(id):
    """Delete a hackathon."""
    try:
        hackathon = json_service.get_by_id('hackathons.json', id)
        if hackathon:
            audit.log_action(
                user=current_user.username,
                action='DELETE_HACKATHON',
                details={'id': id, 'title': hackathon.get('title')}
            )
        
        result = json_service.delete('hackathons.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Hackathon deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Success Stories
# ================================================================

@api_bp.route('/success-stories/', methods=['GET'])
@login_required
def api_get_success_stories():
    """Get all success stories."""
    try:
        stories = json_service.get_all('success_stories.json')
        return jsonify(stories)
    except Exception as e:
        print(f"❌ Error getting success stories: {e}")
        return jsonify([])


@api_bp.route('/success-stories/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_success_story():
    """Create a new success story."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title') or not data.get('sme_name') or not data.get('story'):
            return jsonify({'success': False, 'error': 'Title, SME Name, and Story are required'}), 400
        
        title = sanitize_html(data.get('title', '').strip())
        data['title'] = title
        
        if data.get('sme_name'):
            data['sme_name'] = sanitize_html(data['sme_name'].strip())
        if data.get('story'):
            data['story'] = sanitize_html(data['story'].strip())
        
        if not data.get('slug'):
            data['slug'] = slugify(title)
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('success_stories.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_SUCCESS_STORY',
            details={'title': title}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Success story created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/success-stories/<int:id>', methods=['GET'])
@login_required
def api_get_success_story(id):
    """Get a single success story by ID."""
    story = json_service.get_by_id('success_stories.json', id)
    if not story:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(story)


@api_bp.route('/success-stories/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_success_story(id):
    """Update a success story."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('success_stories.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        if data.get('sme_name'):
            data['sme_name'] = sanitize_html(data['sme_name'].strip())
        if data.get('story'):
            data['story'] = sanitize_html(data['story'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('success_stories.json', id, data)
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_SUCCESS_STORY',
            details={'id': id, 'title': data.get('title')}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Success story updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/success-stories/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_success_story(id):
    """Delete a success story."""
    try:
        story = json_service.get_by_id('success_stories.json', id)
        if story:
            audit.log_action(
                user=current_user.username,
                action='DELETE_SUCCESS_STORY',
                details={'id': id, 'title': story.get('title')}
            )
        
        result = json_service.delete('success_stories.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Success story deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - SME Interest Submissions
# ================================================================

@api_bp.route('/sme-submissions/', methods=['GET'])
@login_required
def api_get_sme_submissions():
    """Get all SME interest submissions."""
    try:
        submissions = json_service.get_all('sme_submissions.json')
        sorted_submissions = sorted(submissions, key=lambda x: x.get('submitted_at', ''), reverse=True)
        return jsonify(sorted_submissions)
    except Exception as e:
        print(f"❌ Error getting SME submissions: {e}")
        return jsonify([])


@api_bp.route('/sme-submissions/', methods=['POST'])
@limiter.limit("10 per minute")
def api_create_sme_submission():
    """Create a new SME interest submission (public endpoint)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate required fields
        required = ['name', 'email', 'organisation', 'industry', 'interest']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Sanitize
        data['name'] = sanitize_html(data.get('name', '').strip())
        data['email'] = sanitize_html(data.get('email', '').strip())
        data['organisation'] = sanitize_html(data.get('organisation', '').strip())
        data['industry'] = sanitize_html(data.get('industry', '').strip())
        data['interest'] = sanitize_html(data.get('interest', '').strip())
        
        if data.get('phone'):
            data['phone'] = sanitize_html(data['phone'].strip())
        if data.get('message'):
            data['message'] = sanitize_html(data['message'].strip())
        
        data['is_read'] = False
        data['submitted_at'] = datetime.now().isoformat()
        
        result = json_service.create('sme_submissions.json', data)
        
        return jsonify({'success': True, 'data': result, 'message': 'Submission received successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/sme-submissions/<int:id>/', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_sme_submission(id):
    """Update an SME submission."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        result = json_service.update('sme_submissions.json', id, data)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_SME_SUBMISSION',
            details={'id': id}
        )
        
        return jsonify({'success': True, 'message': 'Submission updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/sme-submissions/<int:id>/', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_sme_submission(id):
    """Delete an SME submission."""
    try:
        submission = json_service.get_by_id('sme_submissions.json', id)
        if submission:
            audit.log_action(
                user=current_user.username,
                action='DELETE_SME_SUBMISSION',
                details={'id': id}
            )
        
        result = json_service.delete('sme_submissions.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Submission deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/sme-submissions/clear/', methods=['DELETE'])
@limiter.limit("5 per minute")
@login_required
def api_clear_sme_submissions():
    """Delete all SME submissions."""
    try:
        result = json_service.clear_all('sme_submissions.json')
        if result:
            audit.log_action(
                user=current_user.username,
                action='CLEAR_SME_SUBMISSIONS',
                details={}
            )
            return jsonify({'success': True, 'message': 'All submissions cleared successfully'})
        return jsonify({'success': False, 'error': 'Failed to clear submissions'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400




# ================================================================
# API - Community Repositories
# ================================================================

@api_bp.route('/repositories/', methods=['GET'])
@login_required
def api_get_repositories():
    """Get all repositories."""
    try:
        repos = json_service.get_all('repositories.json')
        return jsonify(repos)
    except Exception as e:
        print(f"❌ Error getting repositories: {e}")
        return jsonify([])


@api_bp.route('/repositories/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_repository():
    """Create a new repository."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('name') or not data.get('description') or not data.get('url'):
            return jsonify({'success': False, 'error': 'Name, Description, and URL are required'}), 400
        
        data['name'] = sanitize_html(data['name'].strip())
        data['description'] = sanitize_html(data['description'].strip())
        data['url'] = data['url'].strip()
        
        if data.get('language'):
            data['language'] = sanitize_html(data['language'].strip())
        if data.get('license'):
            data['license'] = sanitize_html(data['license'].strip())
        
        if not data.get('slug'):
            data['slug'] = slugify(data['name'])
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('repositories.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_REPOSITORY',
            details={'name': data['name']}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Repository created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/repositories/<int:id>', methods=['GET'])
@login_required
def api_get_repository(id):
    """Get a single repository by ID."""
    repo = json_service.get_by_id('repositories.json', id)
    if not repo:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(repo)


@api_bp.route('/repositories/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_repository(id):
    """Update a repository."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('repositories.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('name'):
            data['name'] = sanitize_html(data['name'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('repositories.json', id, data)
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_REPOSITORY',
            details={'id': id, 'name': data.get('name')}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Repository updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/repositories/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_repository(id):
    """Delete a repository."""
    try:
        repo = json_service.get_by_id('repositories.json', id)
        if repo:
            audit.log_action(
                user=current_user.username,
                action='DELETE_REPOSITORY',
                details={'id': id, 'name': repo.get('name')}
            )
        
        result = json_service.delete('repositories.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Repository deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Community Events
# ================================================================

@api_bp.route('/community-events/', methods=['GET'])
@login_required
def api_get_community_events():
    """Get all community events."""
    try:
        events = json_service.get_all('community_events.json')
        return jsonify(events)
    except Exception as e:
        print(f"❌ Error getting community events: {e}")
        return jsonify([])


@api_bp.route('/community-events/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_community_event():
    """Create a new community event."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title') or not data.get('date') or not data.get('type') or not data.get('description'):
            return jsonify({'success': False, 'error': 'Title, Date, Type, and Description are required'}), 400
        
        data['title'] = sanitize_html(data['title'].strip())
        data['description'] = sanitize_html(data['description'].strip())
        
        if not data.get('slug'):
            data['slug'] = slugify(data['title'])
        
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('community_events.json', data)
        
        audit.log_action(
            user=current_user.username,
            action='CREATE_COMMUNITY_EVENT',
            details={'title': data['title']}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Event created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/community-events/<int:id>', methods=['GET'])
@login_required
def api_get_community_event(id):
    """Get a single community event by ID."""
    event = json_service.get_by_id('community_events.json', id)
    if not event:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(event)


@api_bp.route('/community-events/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_community_event(id):
    """Update a community event."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('community_events.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('community_events.json', id, data)
        
        audit.log_action(
            user=current_user.username,
            action='UPDATE_COMMUNITY_EVENT',
            details={'id': id, 'title': data.get('title')}
        )
        
        return jsonify({'success': True, 'data': result, 'message': 'Event updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/community-events/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_community_event(id):
    """Delete a community event."""
    try:
        event = json_service.get_by_id('community_events.json', id)
        if event:
            audit.log_action(
                user=current_user.username,
                action='DELETE_COMMUNITY_EVENT',
                details={'id': id, 'title': event.get('title')}
            )
        
        result = json_service.delete('community_events.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Event deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Community Join Submissions
# ================================================================

@api_bp.route('/community-join/', methods=['POST'])
@limiter.limit("10 per minute")
def api_create_community_submission():
    """Create a new community join submission (public endpoint)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate required fields
        required = ['name', 'email', 'role', 'interest']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Sanitize
        data['name'] = sanitize_html(data.get('name', '').strip())
        data['email'] = sanitize_html(data.get('email', '').strip())
        data['role'] = sanitize_html(data.get('role', '').strip())
        data['interest'] = sanitize_html(data.get('interest', '').strip())
        
        if data.get('github'):
            data['github'] = sanitize_html(data['github'].strip())
        if data.get('message'):
            data['message'] = sanitize_html(data['message'].strip())
        
        data['is_read'] = False
        data['submitted_at'] = datetime.now().isoformat()
        
        result = json_service.create('community_submissions.json', data)
        
        return jsonify({'success': True, 'data': result, 'message': 'Join request submitted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/community-submissions/', methods=['GET'])
@login_required
def api_get_community_submissions():
    """Get all community join submissions."""
    try:
        submissions = json_service.get_all('community_submissions.json')
        sorted_submissions = sorted(submissions, key=lambda x: x.get('submitted_at', ''), reverse=True)
        return jsonify(sorted_submissions)
    except Exception as e:
        print(f"❌ Error getting community submissions: {e}")
        return jsonify([])


@api_bp.route('/community-submissions/<int:id>/', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_community_submission(id):
    """Delete a community submission."""
    try:
        submission = json_service.get_by_id('community_submissions.json', id)
        if submission:
            audit.log_action(
                user=current_user.username,
                action='DELETE_COMMUNITY_SUBMISSION',
                details={'id': id}
            )
        
        result = json_service.delete('community_submissions.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Submission deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/community-submissions/clear/', methods=['DELETE'])
@limiter.limit("5 per minute")
@login_required
def api_clear_community_submissions():
    """Delete all community submissions."""
    try:
        result = json_service.clear_all('community_submissions.json')
        if result:
            audit.log_action(
                user=current_user.username,
                action='CLEAR_COMMUNITY_SUBMISSIONS',
                details={}
            )
            return jsonify({'success': True, 'message': 'All submissions cleared successfully'})
        return jsonify({'success': False, 'error': 'Failed to clear submissions'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400




# ================================================================
# API - Replication Resources
# ================================================================

@api_bp.route('/replication-resources/', methods=['GET'])
@login_required
def api_get_replication_resources():
    """Get all replication resources."""
    try:
        resources = json_service.get_all('replication_resources.json')
        return jsonify(resources)
    except Exception as e:
        print(f"❌ Error getting replication resources: {e}")
        return jsonify([])


@api_bp.route('/replication-resources/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_replication_resource():
    """Create a new replication resource."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title') or not data.get('file_path'):
            return jsonify({'success': False, 'error': 'Title and File Path are required'}), 400
        
        data['title'] = sanitize_html(data['title'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        if not data.get('slug'):
            data['slug'] = slugify(data['title'])
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('replication_resources.json', data)
        audit.log_action(user=current_user.username, action='CREATE_REPLICATION_RESOURCE', details={'title': data['title']})
        return jsonify({'success': True, 'data': result, 'message': 'Resource created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/replication-resources/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_replication_resource(id):
    """Update a replication resource."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('replication_resources.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('replication_resources.json', id, data)
        audit.log_action(user=current_user.username, action='UPDATE_REPLICATION_RESOURCE', details={'id': id})
        return jsonify({'success': True, 'data': result, 'message': 'Resource updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/replication-resources/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_replication_resource(id):
    """Delete a replication resource."""
    try:
        resource = json_service.get_by_id('replication_resources.json', id)
        if resource:
            audit.log_action(user=current_user.username, action='DELETE_REPLICATION_RESOURCE', details={'id': id})
        result = json_service.delete('replication_resources.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Resource deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Replication Templates
# ================================================================

@api_bp.route('/replication-templates/', methods=['GET'])
@login_required
def api_get_replication_templates():
    """Get all replication templates."""
    try:
        templates = json_service.get_all('replication_templates.json')
        return jsonify(templates)
    except Exception as e:
        print(f"❌ Error getting replication templates: {e}")
        return jsonify([])


@api_bp.route('/replication-templates/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_replication_template():
    """Create a new replication template."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title') or not data.get('file_path'):
            return jsonify({'success': False, 'error': 'Title and File Path are required'}), 400
        
        data['title'] = sanitize_html(data['title'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        if not data.get('slug'):
            data['slug'] = slugify(data['title'])
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('replication_templates.json', data)
        audit.log_action(user=current_user.username, action='CREATE_REPLICATION_TEMPLATE', details={'title': data['title']})
        return jsonify({'success': True, 'data': result, 'message': 'Template created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/replication-templates/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_replication_template(id):
    """Update a replication template."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('replication_templates.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('replication_templates.json', id, data)
        audit.log_action(user=current_user.username, action='UPDATE_REPLICATION_TEMPLATE', details={'id': id})
        return jsonify({'success': True, 'data': result, 'message': 'Template updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/replication-templates/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_replication_template(id):
    """Delete a replication template."""
    try:
        template = json_service.get_by_id('replication_templates.json', id)
        if template:
            audit.log_action(user=current_user.username, action='DELETE_REPLICATION_TEMPLATE', details={'id': id})
        result = json_service.delete('replication_templates.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Template deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ================================================================
# API - Replication Lessons
# ================================================================

@api_bp.route('/replication-lessons/', methods=['GET'])
@login_required
def api_get_replication_lessons():
    """Get all replication lessons."""
    try:
        lessons = json_service.get_all('replication_lessons.json')
        return jsonify(lessons)
    except Exception as e:
        print(f"❌ Error getting replication lessons: {e}")
        return jsonify([])


@api_bp.route('/replication-lessons/', methods=['POST'])
@limiter.limit("30 per minute")
@login_required
def api_create_replication_lesson():
    """Create a new replication lesson."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not data.get('title') or not data.get('description'):
            return jsonify({'success': False, 'error': 'Title and Description are required'}), 400
        
        data['title'] = sanitize_html(data['title'].strip())
        data['description'] = sanitize_html(data['description'].strip())
        if data.get('content'):
            data['content'] = sanitize_html(data['content'].strip())
        if data.get('subtext'):
            data['subtext'] = sanitize_html(data['subtext'].strip())
        if not data.get('slug'):
            data['slug'] = slugify(data['title'])
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.create('replication_lessons.json', data)
        audit.log_action(user=current_user.username, action='CREATE_REPLICATION_LESSON', details={'title': data['title']})
        return jsonify({'success': True, 'data': result, 'message': 'Lesson created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/replication-lessons/<int:id>', methods=['PUT'])
@limiter.limit("30 per minute")
@login_required
def api_update_replication_lesson(id):
    """Update a replication lesson."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        existing = json_service.get_by_id('replication_lessons.json', id)
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        
        if data.get('title'):
            data['title'] = sanitize_html(data['title'].strip())
        if data.get('description'):
            data['description'] = sanitize_html(data['description'].strip())
        if data.get('content'):
            data['content'] = sanitize_html(data['content'].strip())
        if data.get('subtext'):
            data['subtext'] = sanitize_html(data['subtext'].strip())
        data['updated_at'] = datetime.now().isoformat()
        
        result = json_service.update('replication_lessons.json', id, data)
        audit.log_action(user=current_user.username, action='UPDATE_REPLICATION_LESSON', details={'id': id})
        return jsonify({'success': True, 'data': result, 'message': 'Lesson updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@api_bp.route('/replication-lessons/<int:id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@login_required
def api_delete_replication_lesson(id):
    """Delete a replication lesson."""
    try:
        lesson = json_service.get_by_id('replication_lessons.json', id)
        if lesson:
            audit.log_action(user=current_user.username, action='DELETE_REPLICATION_LESSON', details={'id': id})
        result = json_service.delete('replication_lessons.json', id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True, 'message': 'Lesson deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400




# ================================================================
# Error Handlers for API
# ================================================================

@api_bp.errorhandler(404)
def api_not_found(error):
    return jsonify({'error': 'Resource not found'}), 404


@api_bp.errorhandler(500)
def api_internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500