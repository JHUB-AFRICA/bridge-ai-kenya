# app/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, EmailField, TextAreaField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional


class ContactForm(FlaskForm):
    """General contact form."""
    name = StringField('Name', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    organisation = StringField('Organisation', validators=[Optional()])
    audience = SelectField('I am a...', choices=[
        ('', 'Select your category'),
        ('farmer', 'Farmer / Mushroom Grower'),
        ('student', 'Student'),
        ('developer', 'Developer / Technologist'),
        ('sme', 'SME / Startup'),
        ('researcher', 'Researcher'),
        ('policymaker', 'Policymaker'),
        ('media', 'Media'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired(), Length(min=10)])
    consent = BooleanField('Consent', validators=[DataRequired()])


class TrainingInterestForm(FlaskForm):
    """Training interest form."""
    name = StringField('Name', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional()])
    county = StringField('County/Location', validators=[DataRequired()])
    audience = SelectField('I am a...', choices=[
        ('', 'Select your category'),
        ('farmer', 'Farmer / Mushroom Grower'),
        ('youth', 'Youth'),
        ('student', 'Student'),
        ('entrepreneur', 'Entrepreneur'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    training_interest = SelectField('Training Interest', choices=[
        ('', 'Select training interest'),
        ('smart_mushroom', 'Smart Mushroom Farming'),
        ('iot_sensors', 'IoT Sensors & Monitoring'),
        ('genai', 'GenAI for Agriculture'),
        ('digital_skills', 'Digital Skills'),
        ('entrepreneurship', 'Agri-Entrepreneurship'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    consent = BooleanField('Consent', validators=[DataRequired()])


class MediaRequestForm(FlaskForm):
    """Media request form."""
    name = StringField('Name', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    outlet = StringField('Media Outlet', validators=[DataRequired()])
    request_type = SelectField('Request Type', choices=[
        ('', 'Select request type'),
        ('interview', 'Interview Request'),
        ('press_info', 'Press Information'),
        ('site_visit', 'Site Visit'),
        ('photo_video', 'Photo/Video Request'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    deadline = StringField('Deadline', validators=[Optional()])
    message = TextAreaField('Request Details', validators=[DataRequired(), Length(min=10)])
    consent = BooleanField('Consent', validators=[DataRequired()])