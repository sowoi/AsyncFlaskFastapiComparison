# flaskcelery
WordPress Automatisation with Python Celery, Flask and RabbitMQ 



## Introduction

Flask Video Upload is a web application built with Flask that allows users to upload, transform, create thumbnails, and publish videos to WordPress. This documentation provides detailed information on how to install, configure, and use the application.

![Flask Celery](/img/flaskcelery1.png)
![Flask Celery](/img/flaskcelery2.png)



## Prequisites

You need to install python-poetry, ffmpeg, rabbitmq-server or redis-server beforehand.


## Installation

To install Flask Video Upload, follow these steps:

1. Clone the repository:

     git clone https://github.com/sowoi/flaskcelery.git

2. Change into the project directory:

      cd flaskcelery

3. Install the dependencies:
  
      poetry install


4. Create Systemd Unite files for each process:

   Celery Worker:

   ```
   # celery-flask-worker.service
   [Unit]
   Description=Celery Worker for Flask Application
   After=network.target
   Requires=rabbitmq-server.service
   
   [Service]
   User=<localUser>
   WorkingDirectory=<ScriptFolder>
   TimeoutStartSec=600
   ExecStart=<ScriptFolder>/.venv/bin/celery -A video_flask.celery worker --loglevel=info
   ExecStop=/bin/bash -c "pkill -f 'celery worker'"
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

   ```
   #celery-flower-monitoring.service
   [Unit]
   Description=Flower for Celery Monitoring
   After=network.target
   Requires=rabbitmq-server.service
   
   [Service]
   User=<localUser>
   WorkingDirectory=<ScriptFolder>
   TimeoutStartSec=600
   ExecStart=<ScriptFolder>/.venv/bin/celery -A video_flask.celery flower --loglevel=info
   ExecStop=/bin/bash -c "pkill -f 'celery flowre'"
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
    ```


   ```
   #flask-celery.service
   [Unit]
   Description=Celery Worker for Flask Application
   After=network.target celery-flask-worker.service celery-flower-monitoring.service
   Requires=rabbitmq-server.service
  
   [Service]
   User=<localUser>
   WorkingDirectory=<ScriptFolder>
   ExecStart=<ScriptFolder>/.venv/bin/gunicorn -c gunicorn_config.py video_flask:app
   ExecStop=/bin/bash -c "pkill -f 'gunicorn'"
   Restart=always
  
   [Install]
   WantedBy=multi-user.target
   ```


## Configuration


Before running the application, you need to configure it. Follow these steps:

1. Create a `config.json` file with the following structure:

    ```JSON
      {
        "SECRET_KEY": "your-secret-key",
        "THUMBNAIL_COUNT": 5,
        "CELERY_BROKER": "redis://localhost:6379/0",
        "result_backend": "redis://localhost:6379/0",
        "FLOWER_API_URL": "http://localhost:5555",
        "WORDPRESS_USERNAME": "your-wordpress-username",
        "WORDPRESS_PASSWORD": "your-wordpress-password",
        "WORDPRESS_URL": "https://your-wordpress-site.com",
        "FTP_SERVER": "ftp.example.com",
        "FTP_USERNAME": "your-ftp-username",
        "FTP_PASSWORD": "your-ftp-password"
      }
   ```

2. Customize the configuration values according to your environment.

## Usage


To use Flask Celery, follow these steps:

1. Start the Flask application with gunicorn:

      ```
      gunicorn -c gunicorn_config.py video_flask:ap
      ```
      
2. Access the application in your web browser at `http://localhost:<PortFromConfig.json>`.

3. Upload a video file using the provided form.

4. Follow the on-screen instructions to transform the video, create thumbnails, add metadata, select categories, and publish to WordPress.

Support and Contributions


If you encounter any issues or have suggestions for improvement, please create an issue on the [GitHub repository](https://github.com/sowoi/flaskcelery). Contributions in the form of pull requests are also welcome.


## License


FlaskCelery is licensed under the GNU General Public License v3.0. See [LICENSE](https://github.com/sowoi/flaskcelery/blob/main/LICENSE) for more information.
