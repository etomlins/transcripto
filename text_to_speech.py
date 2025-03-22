import json
import boto3
import os
import uuid
import pathlib
import tempfile
import datatier
import urllib.parse

from configparser import ConfigParser

def lambda_handler(event, context):
    try:
        print("**STARTING**")
        print("**lambda: text-to-speech**")
        
        config_file = 'transcripto-app-config.ini'
        os.environ['AWS_SHARED_CREDENTIALS_FILE'] = config_file
        configur = ConfigParser()
        configur.read(config_file)

        bucketname = configur.get('s3', 'bucket_name')
        s3 = boto3.client('s3')

        rds_endpoint = configur.get('rds', 'endpoint')
        rds_portnum = int(configur.get('rds', 'port_number'))
        rds_username = configur.get('rds', 'user_name')
        rds_pwd = configur.get('rds', 'user_pwd')
        rds_dbname = configur.get('rds', 'db_name')
        dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)

        # Get file from S3 event
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        print("S3 Triggered on:", bucket, key)

        tmp_txt_path = f"/tmp/{os.path.basename(key)}"
        s3.download_file(bucket, key, tmp_txt_path)

        with open(tmp_txt_path, 'r') as f:
            text = f.read()

        # Prepare output file
        filename = "tts-" + str(uuid.uuid4()) + ".mp3"
        local_filename = f"/tmp/{filename}"
        
        datatier.perform_action(dbConn, "UPDATE jobs SET status='processing...' WHERE originaldatafile=%s", (key,))
        # Generate speech
        print("**Synthesizing speech with Polly**")
        polly_client = boto3.client('polly')
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Joanna'
        )

        with open(local_filename, 'wb') as file:
            file.write(response['AudioStream'].read())

        print("**Uploading audio file to S3**")
        s3.upload_file(
            local_filename,
            bucketname,
            filename,
            ExtraArgs={'ACL': 'public-read', 'ContentType': 'audio/mpeg'}
        )

        print("**Logging to database**")
        datatier.perform_action(dbConn, "UPDATE jobs SET status='completed', resultsfilekey=%s WHERE datafilekey=%s", (filename, key))

        sql = "SELECT LAST_INSERT_ID();"
        row = datatier.retrieve_one_row(dbConn, sql)
        jobid = row[0]

        return {
            'statusCode': 200,
            'body': json.dumps({'job_id': jobid, 'results_url': f"https://{bucketname}.s3.amazonaws.com/{filename}"})
        }

    except Exception as err:
        print("**ERROR**", str(err))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(err)})
        }
