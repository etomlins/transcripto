import json
import boto3
import os
import base64
import datatier
from configparser import ConfigParser

def lambda_handler(event, context):
    try:
        print("**STARTING**")
        print("**lambda: transcripto_download**")

        config_file = 'transcripto-app-config.ini'
        os.environ['AWS_SHARED_CREDENTIALS_FILE'] = config_file
        configur = ConfigParser()
        configur.read(config_file)

        s3 = boto3.client('s3')
        bucketname = configur.get('s3', 'bucket_name')

        rds_endpoint = configur.get('rds', 'endpoint')
        rds_portnum = int(configur.get('rds', 'port_number'))
        rds_username = configur.get('rds', 'user_name')
        rds_pwd = configur.get('rds', 'user_pwd')
        rds_dbname = configur.get('rds', 'db_name')
        dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)

        if event.get("queryStringParameters") and "jobid" in event["queryStringParameters"]:
            jobid = event["queryStringParameters"]["jobid"]
        elif event.get("pathParameters") and "jobid" in event["pathParameters"]:
            jobid = event["pathParameters"]["jobid"]
        else:
            raise Exception("Missing jobid in query string or path")

        print("jobid:", jobid)

        sql = "SELECT * FROM jobs WHERE jobid = %s;"
        row = datatier.retrieve_one_row(dbConn, sql, [jobid])

        if not row:
            return {'statusCode': 400, 'body': json.dumps("no such job...")}

        status = row[1]
        jobtype = row[2]
        original_data_file = row[3]
        results_file_key = row[5]

        print("status:", status)
        print("jobtype:", jobtype)
        print("results_file_key:", results_file_key)

        if status == "uploaded":
            return {'statusCode': 480, 'body': json.dumps(status)}
        if status.startswith("processing"):
            return {'statusCode': 481, 'body': json.dumps(status)}
        if status == "error":
            return {'statusCode': 482, 'body': json.dumps("error occurred")}

        if status != "completed":
            msg = f"error: unexpected job status of '{status}'"
            return {'statusCode': 482, 'body': json.dumps(msg)}

        if jobtype == "text_to_speech":
            print("**Returning MP3 download URL**")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'results_url': f"https://{bucketname}.s3.amazonaws.com/{results_file_key}"
                })
            }

        elif jobtype == "transcription":
            print("**Downloading transcription JSON from S3**")
            local_filename = "/tmp/results.txt"
            s3.download_file(bucketname, results_file_key, local_filename)

            with open(local_filename, "r") as infile:
                transcript_json = json.load(infile)

            transcript_text = transcript_json['results']['transcripts'][0]['transcript']

            print("**DONE, returning transcript**")
            return {
                'statusCode': 200,
                'body': json.dumps(transcript_text)
            }

        else:
            return {'statusCode': 400, 'body': json.dumps("Unsupported job type.")}

    except Exception as err:
        print("**ERROR**", str(err))
        return {
            'statusCode': 500,
            'body': json.dumps(str(err))
        }
