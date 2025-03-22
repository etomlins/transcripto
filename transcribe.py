import json
import boto3
import os
import uuid
import base64
import pathlib
import tempfile
import urllib.parse
import time
import datatier

from configparser import ConfigParser


def lambda_handler(event, context):
    try:
        print("**STARTING**")
        print("**lambda: transcribe**")
        
        # 
        # in case we get an exception, initial this filename
        # so we can write an error message if need be:
        #
        bucketkey_results_file = ""
        
        #
        # setup AWS based on config file:
        #
        config_file = 'transcripto-app-config.ini'
        os.environ['AWS_SHARED_CREDENTIALS_FILE'] = config_file
        
        configur = ConfigParser()
        configur.read(config_file)
        
        bucketname = configur.get('s3', 'bucket_name')
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucketname)
        #
        # configure for RDS access
        #
        rds_endpoint = configur.get('rds', 'endpoint')
        rds_portnum = int(configur.get('rds', 'port_number'))
        rds_username = configur.get('rds', 'user_name')
        rds_pwd = configur.get('rds', 'user_pwd')
        rds_dbname = configur.get('rds', 'db_name')
        
        # get bucket and key name
        s3_bucket = event['Records'][0]['s3']['bucket']['name']
        s3_key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

        dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)
        datatier.perform_action(dbConn, "UPDATE jobs SET status='processing...' WHERE originaldatafile=%s", (s3_key,))

        print(f"Key: {s3_key} and Bucket: {s3_bucket}")
        bucketkey = s3_key

        # check valid 
        if not s3_key.endswith('.mp3'):
            return {
                'statusCode': 400,
                'body': json.dumps({'message': "must be an mp3"})
            }


        job = pathlib.Path(s3_key).stem.replace(".", "_").replace("-", "_") + "_" + str(uuid.uuid4())
        output_file = f"{job}.txt"
        
        transcribe_client = boto3.client('transcribe')
        s3_uri = f"s3://{s3_bucket}/{s3_key}"
        
        response = transcribe_client.start_transcription_job(
            TranscriptionJobName=job,
            LanguageCode='en-US',
            Media={
                'MediaFileUri': s3_uri
            },
            OutputBucketName=s3_bucket,
            OutputKey=output_file
        )
        
        print(f"Transcription job started with name: {job}")

        while True:
            print("***Waiting for transcription job to complete...")
            status = transcribe_client.get_transcription_job(TranscriptionJobName=job)
            job_status = status['TranscriptionJob']['TranscriptionJobStatus']
            
            if job_status == 'COMPLETED':
                print("Updating DB to complete for originaldatafile =", s3_key)
                datatier.perform_action(dbConn, "UPDATE jobs SET status='completed', resultsfilekey=%s WHERE datafilekey=%s", (output_file, s3_key))
                break
            elif job_status == 'FAILED':
                datatier.perform_action(dbConn, "UPDATE jobs SET status='error', resultsfilekey='' WHERE datafilekey=%s", (s3_key,))

            time.sleep(5)

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Transcription job started', 'job_name': job})
        }    
    except Exception as err:
        print("**ERROR**", str(err))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(err)})
        }
