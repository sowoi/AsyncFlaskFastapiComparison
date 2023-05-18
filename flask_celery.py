from flask import Flask, request, send_from_directory, redirect, url_for, session, render_template, flash, jsonify
import os
import subprocess
import uuid
import random
import base64
import requests
from datetime import datetime, date
from ftplib import FTP
import ssl
from unidecode import unidecode
import re
import time
import logging
import json
from celery import Celery
from celery.result import AsyncResult


with open('config.json') as f:
    config = json.load(f)

app = Flask(__name__)


UPLOAD_FOLDER = os.path.join(os.getcwd(), 'upload')
THUMBNAIL_COUNT = config['THUMBNAIL_COUNT']

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = config['SECRET_KEY']
app.config['CELERY_broker_url'] = config['CELERY_BROKER']
app.config['result_backend'] = config['result_backend']

celery = Celery(app.name, broker=app.config['CELERY_broker_url'])
celery.conf.update(app.config)

handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)


@app.before_request
def start_timer():
    request.start_time = time.time()


@app.after_request
def log_time(response):
    # don't consider the time if the request failed
    if response.status_code == 200:
        elapsed_time = time.time() - request.start_time
        app.logger.info("Elapsed time: %f seconds" % elapsed_time)
    return response


@app.route('/upload', methods=['POST'])
def upload():
    """Handle the file upload endpoint."""
    file = request.files['video']
    if file:
        filename = str(uuid.uuid4())
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        chunk_size = 4096
        with open(file_path, 'wb') as f:
            while True:
                chunk = file.stream.read(chunk_size)
                if len(chunk) == 0:
                    break
                f.write(chunk)
        return jsonify({'redirect_url': url_for('ffmpeg_process', filename=filename)}), 200
    else:
        return {'error': 'No file uploaded'}, 400


@app.route('/', methods=['GET', 'POST'])
def index():
    """Handle the index page."""
    uuid_dict = {}
    if request.method == 'POST':
        filesDict = request.files.to_dict()
        file = request.files['video']
        if not file:
            error_message = "Bitte gib ein Video an!"
            return render_template('index.html', error_message=error_message)
        filename = str(uuid.uuid4())
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        session['video_filename'] = filename
        flash('Upload vollständig!')
        flash('Im nächsten Schritt wird umgewandelt!')
        return render_template('transition.html', filename=filename, stepdescription="Schritt 2 von 7: Video umwandeln", redirect_url=url_for('ffmpeg_process', filename=filename))
    for filename in os.listdir(UPLOAD_FOLDER):
        match_temp = re.match(r"(.*)-temp\.mp4", filename)
        if match_temp:
            uuid_name = match_temp.group(1)
            if uuid_name not in uuid_dict:
                uuid_dict[uuid_name] = {"temp": 1, "thumbs": 0}
            else:
                uuid_dict[uuid_name]["temp"] += 1

        match_thumb = re.match(r"thumbnail_\d+_(.*)\.png", filename)
        if match_thumb:
            uuid_name = match_thumb.group(1)
            if uuid_name not in uuid_dict:
                uuid_dict[uuid_name] = {"temp": 0, "thumbs": 1}
            else:
                uuid_dict[uuid_name]["thumbs"] += 1
    api_url = config['FLOWER_API_URL']
    response = requests.get(api_url)
    if response.status_code == 200:
        task_data = response.json()
        #task_dict = json.loads(task_data)
        running_tasks = task_data
    return render_template('index.html', uuid_dict=uuid_dict, running_tasks=running_tasks)


@app.route('/ffmpeg_process/<filename>', methods=['GET', 'POST'])
def ffmpeg_process(filename):
    """Handle the ffmpeg process for video transformation and creation of thumbnails."""
    logging.info("FFMPEG_processing")
    temp_output_filename = filename + "-temp.mp4"
    session['temp_output_filename'] = temp_output_filename
    result = transform_video.delay(filename, temp_output_filename)
    video_transform_task_id = result.id
    session['video_transform_task_id'] = video_transform_task_id
    flash('Umwandlung wird im Hintergrund weitererledigt!')
    flash('Im nächsten Schritt werden die Thumbnails erstellt.')
    return render_template('transition.html', filename=filename, stepdescription="Schritt 3 von 7: Thumbnails erstellen", redirect_url=url_for('create_thumbnail', filename=filename))

    
@app.route('/create_thumbnail/<filename>', methods=['GET', 'POST'])
def create_thumbnail(filename):
    """Handle the creation of thumbnails for the video."""
    logging.info("creating thumbnails...")
    thumbnail_filenames = []

    futures = [create_single_thumbnail.delay(i, filename) for i in range(THUMBNAIL_COUNT)]
    for future in futures:
        thumbnail_filenames.append(future.get())
            

    session['thumnbail_filenames'] = ','.join(thumbnail_filenames)
    flash('Im nächsten Schritt wählst du ein Thumbnail aus.')
    return render_template('transition.html', filename=filename, stepdescription="Schritt 4 von 7: Thumbnail auswählen", redirect_url=url_for('choose_thumbnail', filename=filename))


@app.route('/choose_thumbnail/<filename>', methods=['GET', 'POST'])
def choose_thumbnail(filename):
    """Reads the created thumbnails and renders them."""
    thumnbail_filenames = session.get('thumnbail_filenames', None)
    filenames = thumnbail_filenames.split(',')
    video_filename = filename
    return render_template('choose_thumbnail.html', filenames=filenames, filename=filename)

@app.route('/select_thumbnail/<filename>')
def select_thumbnail(filename):
    """Thumbnail selection. The rest will be deleted."""
    thumbnail_filename = request.args.get('thumbnail')
    session['thumbnail_filename']  = thumbnail_filename
 
    # Delete other thumbnails
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.startswith('thumbnail_') and file != thumbnail_filename and filename in file:
            logging.info(f"deleted thumbnail {file}")
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file))
            
    command = ['convert', os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename), '-resize', '500x500>',  '-quality', '80%', '-depth', '8', '-type', 'Palette', '-strip', os.path.join(app.config['UPLOAD_FOLDER'],thumbnail_filename)]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Command `{e.cmd}` exited with status code {e.returncode}")
        if e.stdout:
            print(f"Output: {e.stdout.decode()}")
        if e.stderr:
            print(f"Error: {e.stderr.decode()}")    
            print("converted file to smaller size")           
    flash('Im nächsten Schritt gibst du Videobeschreibung und Videodatum an.')
    select_thumbnail_task.delay(filename)
    return render_template('transition.html', filename=filename, stepdescription="Schritt 5 von 7: Metadaten übermitteln", redirect_url=url_for('add_meta', filename=filename))
    

@app.route('/add_meta/<filename>', methods=['GET', 'POST'])
def add_meta(filename):
    """ User input for summary and publishing date. """
    today = date.today().strftime('%Y-%m-%d')
    if request.method == 'POST':
        summary = request.form.get('summary')
        session['summary'] = summary    
        video_date = request.form.get('date')
        if not summary:
            error_message = "Bitte gib  eine Videobeschreibung ein."
            return render_template('add_meta.html', categories=categories, current_year=current_year, error_message=error_message)


        # Generate filename from selected date if provided, otherwise use current date
        date_for_filename = video_date if video_date else datetime.today().strftime('%y-%m-%d')
        summary = unidecode(summary)
        summary_slug = summary.lower().replace(' ', '-')
        slug_output_filename = f"{date_for_filename}-{summary_slug}.mp4"
        session['slug_video_name'] = slug_output_filename
        
        if video_date:
            session['video_date'] = video_date
        else:
            session['video_date'] = datetime.today().strftime('%Y-%m-%d')
        flash('Im nächsten Schritt gibst du die Kategorien an.')
        add_meta_task.delay(filename, slug_output_filename, video_date)
        return render_template('transition.html', filename=filename, stepdescription="Schritt 6 von 7: Kategorien auwählen", redirect_url=url_for('select_categories', filename=filename))
    
    return render_template('add_meta.html',today=today)
     
            
@app.route('/select_categories/<filename>', methods=['GET', 'POST'])
def select_categories(filename):
    """ User input for wordpress categories. """
    username = config['WORDPRESS_USERNAME']
    password = config['WORDPRESS_PASSWORD']
    url = config['WORDPRESS_URL']+'/wp-json/wp/v2/categories?per_page=100'
    current_year = str(datetime.now().year)
    response = requests.get(url, auth=(username, password))
    categories = response.json()
    
    if request.method == 'POST':
        selected_categories = request.form.getlist('categories')
        session['selected_categories'] = selected_categories
        flash('Jetzt wird alles im Hintergrund erledigt.')
        select_categories_task.delay(filename, selected_categories)
        return render_template('transition.html', filename=filename, stepdescription="Schritt 7 von 7: An Wordpress übermitteln", redirect_url=url_for('background_process', filename=filename))
    return render_template('select_categories.html', categories=categories, current_year=current_year)
    
@app.route('/background_process/<filename>')
def background_process(filename):
    """ Background processes handled be celary """
    temp_video_filename = session.get('temp_output_filename', None)
    video_transform_task_id = session.get('video_transform_task_id', None)
    slug_video_filename = session.get('slug_video_name', None)
    thumbnail_file = session.get('thumbnail_filename', None)
    summary = session.get('summary', None)
    categories = session.get('selected_categories', None)
    video_date = session.get('video_date', None)
    background_process_handler(filename, temp_video_filename,video_transform_task_id, slug_video_filename, thumbnail_file, summary, categories, video_date)
    return redirect(url_for('status_message', filename=filename))


@app.route('/status_message/<filename>')
def status_message(filename):
    """ Checks if the last task is finished. """
    background_tasks_finished_id = session.get('background_tasks_finished_id', None)
    background_tasks_finished_state = AsyncResult(background_tasks_finished_id, app=celery)
    if background_tasks_finished_state.status == 'SUCCESS':
        return render_template('send_to_wordpress.html', filename=filename, message="Video send to Wordpress successfully.")
    else:
        return render_template('send_to_wordpress.html', filename=filename, message="Video is still processing.")


@app.route('/uploads/<filename>')
def send_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def page_not_found(e):
    return render_template('404.html'), 500


def background_process_handler(filename, temp_video_filename,video_transform_task_id, slug_video_filename, thumbnail_file, summary, categories, video_date):
    video_transform_task_state = AsyncResult(video_transform_task_id, app=celery)
    video_transform_task_state.get() 
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))  #
    # rename temp video filename to slug video filename
    command = ['mv', os.path.join(app.config['UPLOAD_FOLDER'], temp_video_filename), os.path.join(app.config['UPLOAD_FOLDER'], slug_video_filename)]
    subprocess.run(command, check=True)

    result = ftp_upload.delay(slug_video_filename, filename)
    ftp_upload_task_id = result.id

    ftp_upload_task_state = AsyncResult(ftp_upload_task_id, app=celery)
    ftp_upload_task_state.get()
    
    current_time = datetime.now().strftime('T%H:%M:%S')
    video_date = video_date + current_time
    
    result = send_to_wordpress.delay(slug_video_filename, thumbnail_file, summary, categories, video_date, filename)
    send_to_wordpress_task_id = result.id

    send_to_wordpress_task_state = AsyncResult(send_to_wordpress_task_id, app=celery)
    send_to_wordpress_task_state.get()
    
    result = delete_redundant_files.delay(slug_video_filename, thumbnail_file, filename)
    delete_redundant_files_task_id = result.id
    delete_redundant_files_task_state = AsyncResult(delete_redundant_files_task_id, app=celery)
    delete_redundant_files_task_state.get()
    
    result = background_tasks_finished.delay(filename)
    background_tasks_finished_id = result.id
    session['background_tasks_finished_id'] = background_tasks_finished_id   

    return True


@celery.task
def create_single_thumbnail(i, filename):
    """ Creates a single thumbnail """
    thumbnail_filename = f"thumbnail_{i}_" + filename + ".png"
    timestamp = str(random.randint(1, 10))
    command = ['ffmpeg', '-y', '-i', os.path.join(app.config['UPLOAD_FOLDER'], filename), '-ss', timestamp, '-vframes', '1', os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename)]
    subprocess.run(command, check=True)
    create_single_thumbnail.filename = filename
    return thumbnail_filename


@celery.task
def transform_video(filename, output_filename): 
        """ Transforms video to Web viewable output. """
        logging.info("Video processing started")
        command = ['ffmpeg', '-y', '-i', os.path.join(app.config['UPLOAD_FOLDER'], filename), '-c:v', 'libx264', '-crf', '29', '-movflags', 'faststart', '-map_metadata', '0', os.path.join(app.config['UPLOAD_FOLDER'], output_filename)]
        subprocess.run(command, check=True)
        transform_video.filename = filename


@celery.task
def ftp_upload(video_filename, filename):
    """ Uploads video via FTP (still the only solution for larger files). """
    logging.info("Starting FTP upload")
    ftp = FTP(config['FTP_SERVER'])  # replace with your FTP server
    ftp.login(config['FTP_USERNAME'], config['FTP_PASSWORD'])
    with open(os.path.join(app.config['UPLOAD_FOLDER'], video_filename), 'rb') as f:
        ftp.storbinary('STOR ' + video_filename, f)
    ftp.quit()
    ftp_upload.filename = filename
  
       
@celery.task
def send_to_wordpress(slug_video_filename, thumbnail_file, summary, categories, video_date, filename):
    """ Posts Wordpress post. """
    url = config['WORDPRESS_URL']
    username = config['WORDPRESS_USERNAME']
    password = config['WORDPRESS_PASSWORD']

    data = open(os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_file), 'rb').read()
    response = requests.post(url=url+"/wp-json/wp/v2/media",
                    data=data,
                    headers={'Content-Type': '', 'Content-Disposition': 'attachment; filename={}'.format(thumbnail_file)},
                    auth=(username, password))
    response_json = response.json()
    thumbnail_id = response_json['id']
    logging.info(thumbnail_id)
    thumbnail_source = response_json['source_url']
    logging.info(thumbnail_source)

    # Set the API endpoint
    url = config['WORDPRESS_URL']
    credentials = username + ':' + password
    token = base64.b64encode(credentials.encode())
    headers = {'Authorization': 'Basic ' + token.decode('utf-8')}
    # Set the data for the new post
    content = f'''[evp_embed_video url=\"{ url }/wp-content/uploads/videos/{ slug_video_filename }\" template="mediaelement" poster=\"{thumbnail_source}\"]

    {summary}'''

    data = {
        'content': content,
        'status': 'publish',
        'featured_media': thumbnail_id,
        'format': 'video',
        'categories': categories,
        'date': video_date
    }

    # Send the POST request
    requests.post(url+"/wp-json/wp/v2/posts", headers=headers, json=data)
    send_to_wordpress.filename = filename


@celery.task
def delete_redundant_files(slug_video_filename, thumbnail_file, filename):
    """ Deletes all redundant files. """
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], slug_video_filename)) 
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_file))
    delete_redundant_files.filename = filename


@celery.task
def background_tasks_finished(filename):
    """ Just a state task for logging in RabbitMQ. """
    logging.info("All background processes finished")
    background_tasks_finished.filename = filename


@celery.task
def add_meta_task(filename):
    """ Just a state task for logging in RabbitMQ. """
    logging.info("Add meta task finished")
    add_meta_task.filename = filename
  
    
@celery.task
def select_thumbnail_task(filename):
    """ Just a state task for logging in RabbitMQ. """
    logging.info("Select thumbnail task finished")
    select_categories_task.filename = filename
    
    
@celery.task
def select_categories_task(filename):
    """ Just a state task for logging in RabbitMQ. """
    logging.info("Select categories task finished")
    select_categories_task.filename = filename
 
 
if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(config['SERVER_HOST'], config['SERVER_HOST'])
    app.run(host=config['SERVER_HOST'], port=config['SERVER_PORT'], debug=True, ssl_context=context)

