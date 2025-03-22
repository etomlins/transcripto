import json
import boto3
import os
import uuid
import datatier

from configparser import ConfigParser

def lambda_handler(event, context):
    try:
        print("**STARTING**")
        print("**lambda: translate via API**")

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

        if "body" not in event:
            raise Exception("Missing body in request")

        body = json.loads(event["body"])
        if "text" not in body or "target_language" not in body:
            raise Exception("Request must include 'text' and 'target_language' fields")

        text = body["text"]
        target_lang = body["target_language"]

        print("**Translating text**")
        translate_client = boto3.client('translate')
        response = translate_client.translate_text(
            Text=text,
            SourceLanguageCode='auto',
            TargetLanguageCode=target_lang
        )

        translated_text = response['TranslatedText']
        filename = f"translated-{str(uuid.uuid4())}.txt"
        local_path = f"/tmp/{filename}"

        with open(local_path, 'w') as f:
            f.write(translated_text)

        print("**Uploading translated file to S3**")
        s3.upload_file(
            local_path,
            bucketname,
            filename,
            ExtraArgs={'ACL': 'public-read', 'ContentType': 'text/plain'}
        )

        print("**Logging to database**")
        sql = """
            INSERT INTO jobs (jobtype, status, originaldatafile, datafilekey, resultsfilekey)
            VALUES ('translation', 'completed', %s, %s, %s);
        """
        datatier.perform_action(dbConn, sql, [filename, filename, filename])

        sql = "SELECT LAST_INSERT_ID();"
        row = datatier.retrieve_one_row(dbConn, sql)
        jobid = row[0]

        return {
            'statusCode': 200,
            'body': json.dumps({
                'job_id': jobid,
                'results_url': f"https://{bucketname}.s3.amazonaws.com/{filename}"
            })
        }

    except Exception as err:
        print("**ERROR**", str(err))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(err)})
        }
