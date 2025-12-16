
import os
import shutil
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_admin.contrib.fileadmin import FileAdmin
from flask_admin.form.upload import ImageUploadField, FileUploadField
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
# from celery import Celery

# --- Basic App and Path Setup ---
_basedir = os.path.abspath(os.path.dirname(__file__))

# --- Paths ---
final_upload_path = os.path.join(_basedir, 'src/static/uploads')
tmp_upload_path = os.path.join(_basedir, 'tmp/uploads')
# celery_out_path = os.path.join(_basedir, 'tmp/celery/out')
# celery_processed_path = os.path.join(_basedir, 'tmp/celery/processed')
instance_path = os.path.join(_basedir, 'instance')
db_uri = 'sqlite:///' + os.path.join(instance_path, 'database.db')

# Ensure all necessary directories exist
# try:
#     os.makedirs(final_upload_path, exist_ok=True)
#     os.makedirs(tmp_upload_path, exist_ok=True)
#     # os.makedirs(celery_out_path, exist_ok=True)
#     # os.makedirs(celery_processed_path, exist_ok=True)
#     os.makedirs(instance_path, exist_ok=True)
# except OSError as e:
#     print(f"Error creating directories: {e}")

# --- Celery Configuration ---
# def make_celery(app):
#     celery = Celery(
#         app.import_name,
#         backend=app.config['CELERY_RESULT_BACKEND'],
#         broker=app.config['CELERY_BROKER_URL']
#     )
#     celery.conf.update(app.config)
#     class ContextTask(celery.Task):
#         def __call__(self, *args, **kwargs):
#             with app.app_context():
#                 return self.run(*args, **kwargs)
#     celery.Task = ContextTask
#     return celery

# --- Flask App Initialization ---
app = Flask(__name__, template_folder='src/templates', static_folder='src/static')
app.config.update(
    SQLALCHEMY_DATABASE_URI=db_uri,
    SECRET_KEY='mysecretkey',
    # CELERY_BROKER_URL='filesystem://',
    # CELERY_RESULT_BACKEND=f'db+{db_uri}',
    # BROKER_TRANSPORT_OPTIONS={
    #     'data_folder_in': celery_out_path,
    #     'data_folder_out': celery_out_path,
    #     'processed_folder': celery_processed_path,
    # }
)

# celery = make_celery(app)
db = SQLAlchemy(app)

# --- Celery Background Task ---
# @celery.task(name='process_media')
def process_media(temp_path, final_filename):
    final_path = os.path.join(final_upload_path, final_filename)
    file_ext = os.path.splitext(final_filename)[1].lower()
    try:
        if file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
            with Image.open(temp_path) as img:
                img = ImageOps.exif_transpose(img)
                max_width = 1920
                if img.width > max_width:
                    ratio = max_width / float(img.width)
                    height = int(float(img.height) * float(ratio))
                    img = img.resize((max_width, height), Image.LANCZOS)
                img.save(final_path, optimize=True, quality=85)
        else:
            shutil.move(temp_path, final_path)
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception as e:
        print(f"Error processing {temp_path}: {e}")

# --- Database Models ---
class ProjectImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(128), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)

class ProjectVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(128), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    images = relationship('ProjectImage', backref='project', cascade="all, delete-orphan")
    videos = relationship('ProjectVideo', backref='project', cascade="all, delete-orphan")
    
    @property
    def thumbnail(self):
        if self.images:
            return self.images[0].path
        return None

class SiteContent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    about_us = db.Column(db.Text, nullable=True)
    contact_info = db.Column(db.Text, nullable=True)

# --- Admin Panel Customization ---
class QuickSaveUploadField(FileUploadField):
    def _save_file(self, data, filename):
        secured_filename = secure_filename(filename)
        temp_full_path = os.path.join(self.base_path, secured_filename)
        data.save(temp_full_path)
        # process_media.delay(temp_full_path, secured_filename)
        process_media(temp_full_path, secured_filename) # Call function directly
        return secured_filename

class QuickSaveImageUploadField(ImageUploadField, QuickSaveUploadField): pass

class ProjectView(ModelView):
    inline_models = (
        (ProjectImage, {'form_label': 'Image', 'form_extra_fields': {'path': QuickSaveImageUploadField('Upload Image', base_path=tmp_upload_path, relative_path='', thumbnail_size=(100, 100, True))}}),
        (ProjectVideo, {'form_label': 'Video', 'form_extra_fields': {'path': QuickSaveUploadField('Upload Video', base_path=tmp_upload_path)}})
    )
    column_list = ('title', 'description')

# --- App Initialization & DB Setup ---
admin = Admin(app, name='Admin Panel')
admin.add_view(ProjectView(Project, db.session))
admin.add_view(ModelView(SiteContent, db.session))
admin.add_view(FileAdmin(final_upload_path, '/static/uploads/', name='Uploaded Files'))

# with app.app_context():
#     db.create_all()
#     if not SiteContent.query.first():
#         default_content = SiteContent(about_us="Welcome...", contact_info="Contact us...")
#         db.session.add(default_content)
#         db.session.commit()

# --- Routes ---
@app.route("/")
def index(): 
    site_content = SiteContent.query.first()
    projects = Project.query.order_by(Project.id.desc()).limit(3).all()
    return render_template('index.html', site_content=site_content, projects=projects)

@app.route("/portfolio")
def portfolio(): 
    projects = Project.query.all()
    return render_template('portfolio.html', projects=projects)

@app.route("/project/<int:project_id>")
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('project_detail.html', project=project)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)
