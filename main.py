#
# Client-side python app for my TRANSCRIPTO APP, which is calling
# a set of lambda functions in AWS through API Gateway.
# The overall purpose of the app is to process audio and text files and
# translate between them.
#
# Authors:
#   Ellen Tomlins
#
#   Prof. Joe Hummel (initial template)
#   Northwestern University
#   CS 310
#

import random
import requests
import jsons

import uuid
import pathlib
import logging
import sys
import os
import base64
import time

from configparser import ConfigParser


############################################################
#
# classes
#
class User:

  def __init__(self, row):
    self.userid = row[0]
    self.username = row[1]
    self.pwdhash = row[2]


class Job:

  def __init__(self, row):
    self.jobid = row[0]
    self.userid = row[1]
    self.status = row[2]
    self.originaldatafile = row[3]
    self.datafilekey = row[4]
    self.resultsfilekey = row[5]


###################################################################
#
# web_service_get
#
# When calling servers on a network, calls can randomly fail. 
# The better approach is to repeat at least N times (typically 
# N=3), and then give up after N tries.
#
def web_service_get(url):
  """
  Submits a GET request to a web service at most 3 times, since 
  web services can fail to respond e.g. to heavy user or internet 
  traffic. If the web service responds with status code 200, 400 
  or 500, we consider this a valid response and return the response.
  Otherwise we try again, at most 3 times. After 3 attempts the 
  function returns with the last response.
  
  Parameters
  ----------
  url: url for calling the web service
  
  Returns
  -------
  response received from web service
  """

  try:
    retries = 0
    
    while True:
      response = requests.get(url)
        
      if response.status_code in [200, 400, 480, 481, 482, 500]:
        #
        # we consider this a successful call and response
        #
        break;

      #
      # failed, try again?
      #
      retries = retries + 1
      if retries < 3:
        # try at most 3 times
        time.sleep(retries)
        continue
          
      #
      # if get here, we tried 3 times, we give up:
      #
      break

    return response

  except Exception as e:
    print("**ERROR**")
    logging.error("web_service_get() failed:")
    logging.error("url: " + url)
    logging.error(e)
    return None
    

############################################################
#
# prompt
#
def prompt():
  """
  Prompts the user and returns the command number

  Parameters
  ----------
  None

  Returns
  -------
  Command number entered by user (0, 1, 2, ...)
  """
  try:
    print()
    print(">> Enter a command:")
    print("   0 => end")
    print("   1 => upload a file")
    print("   2 => get status of a job")
    print("   3 => upload and poll")
    print("   4 => translate")

    cmd = input()

    if cmd == "":
      cmd = -1
    elif not cmd.isnumeric():
      cmd = -1
    else:
      cmd = int(cmd)

    return cmd

  except Exception as e:
    print("**ERROR")
    print("**ERROR: invalid input")
    print("**ERROR")
    return -1

##############################################################
##############################################################
##############################################################
def upload_file(baseurl):
    """
    Upload mp3 or txt file to be processed (either transcribed or text-to-speech).

    Parameters
    ----------
    baseurl: str

    Returns
    -------
    jobid
    """
    
    api = '/upload'
    url = baseurl + api
    
    print("Enter local path to file:")
    path = input().strip()

    try:
        with open(path, "rb") as file:
            file_bytes = file.read()
    except FileNotFoundError:
        print("error: file not found")
        return

    extension = path.split('.')[-1].lower()
    job_type = input("Enter job type (transcription or text_to_speech): ").strip().lower()

    if job_type not in {"transcription", "text_to_speech"}:
        print("error: invalid job type")
        return
    if extension not in {'mp3','txt'}:
        print("error: only mp3 and txt files for now")
        return

    encoded = base64.b64encode(file_bytes).decode("utf-8")
    filename = path.split("/")[-1]

    payload = {
        "filename": filename,
        "data": encoded
    }

    params = {"job_type": job_type}

    headers = {
        "Content-Type": "application/json"
    }

    print(f"Uploading {filename} as a {job_type} job...")

    response = requests.post(url, json=payload, params=params, headers=headers)

    if response.status_code == 200:
        print("Success!")
        print(response.json())
    else:
        print(f"Failed with status code: {response.status_code}")
        print(response.text)

def get_status(baseurl):
  """
  get status of a job
  
  Parameters
  ----------
  baseurl: str

  Returns
  -------
  status of job

  """
  print("enter jobid> ")
  jobid = input().strip()
  url = f"{baseurl}/results/{jobid}/"
  print('url: ', url)
  response = requests.get(url)
  
  status_code = response.status_code
  print('status code: ', status_code)
  
  if status_code == 200:
      transcript = response.json()
      print('status: completed')
      print(transcript)
      return transcript
  elif status_code == 480:
      print('status: uploaded')
      return 'uploaded'
  elif status_code == 481:
      print('status: processing')
      return 'processing'
  elif status_code == 482:
      error_msg = response.json()
      print('error:')
      print(error_msg)
      return 'error'
  elif status_code == 400:
      print('job id not found.')
      return 'wrong id'
  else:
      print('weird error bro')

def upload_and_poll(baseurl):
  try:
      error = False

      api = '/upload'
      url = baseurl + api

      print("Enter local path to file:")
      path = input().strip()

      try:
          with open(path, "rb") as file:
              file_bytes = file.read()
      except FileNotFoundError:
          print("Error: File not found.")
          return

      extension = path.split('.')[-1].lower()
      job_type = input("Enter job type (transcription or text_to_speech): ").strip().lower()

      if job_type not in {"transcription", "text_to_speech"}:
          print("Error: invalid job type.")
          return

      encoded = base64.b64encode(file_bytes).decode("utf-8")
      filename = path.split("/")[-1]
      
      payload = {
          "filename": filename,
          "data": encoded
      }

      params = {"job_type": job_type}
      headers = {"Content-Type": "application/json"}

      print(f"Uploading {filename} as a {job_type} job...")
      response = requests.post(url, json=payload, params=params, headers=headers)

      if response.status_code != 200:
          print(f"Upload failed with status code: {response.status_code}")
          print(response.text)
          return

      jobid = response.json()
      print("Upload succeeded. Job ID:", jobid)

      result_url = f"{baseurl}/results/{jobid}/"

      while True:
          res = requests.get(result_url)
          status_code = res.status_code
          msg = res.json()

          print("Status code:", status_code)

          if status_code == 200:
              break

          if 400 <= status_code < 500:
              print("Job status:", msg)

          if 'error' in msg or status_code >= 500:
              error = True
              break

          time.sleep(random.randint(1, 5))

      if error:
          print("Job failed or encountered error:")
          print(msg)
          return

      if job_type == "transcription":
          print("TRANSCRIPTION RESULTS BELOW:\n")
          print(msg)

      elif job_type == "text_to_speech":
          mp3_url = msg.get("results_url")
          if not mp3_url:
              print("Unexpected response for text_to_speech job:", msg)
              return

          output_filename = f"tts-result-{jobid}.mp3"
          print("Downloading MP3 file from:", mp3_url)
          audio = requests.get(mp3_url)
          with open(output_filename, 'wb') as f:
              f.write(audio.content)

          print(f"Audio saved to: {output_filename}")

      else:
          print("Unsupported job type in client handler.")

  except Exception as e:
      logging.error("**ERROR: upload_and_poll() failed:")
      logging.error(e)
      return

def translate(baseurl):
  try:
    api = '/translate'
    url = baseurl + api
        
    path = input("Enter local path to .txt file: ").strip()
    lang = input("Enter target language ('es' = Spanish, 'fr' = French): ").strip()

    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print("Error: wrong path.")
        return

    payload = {
        "text": text,
        "target_language": lang
    }

    headers = {"Content-Type": "application/json"}

    print(f"Sending file for translation to '{lang}'...")

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        res = response.json()
        print("Job ID:", res["job_id"])
        
        print("TRANSLATION RESULTS BELOW:\n")
        translation = requests.get(res["results_url"])
        print(translation.text)
    else:
        print("Failed with status code:", response.status_code)
        print(response.text)
  except Exception as e:
      logging.error("**ERROR: upload_and_poll() failed:")
      logging.error(e)
      return



############################################################
# main
#
try:
  print('** Welcome to Transcripto! **')
  print()

  # eliminate traceback so we just get error message:
  sys.tracebacklimit = 0

  #
  # what config file should we use for this session?
  #
  config_file = 'transcripto-client-config.ini'

  print("Config file to use for this session?")
  print("Press ENTER to use default, or")
  print("enter config file name>")
  s = input()

  if s == "":  # use default
    pass  # already set
  else:
    config_file = s

  #
  # does config file exist?
  #
  if not pathlib.Path(config_file).is_file():
    print("**ERROR: config file '", config_file, "' does not exist, exiting")
    sys.exit(0)

  #
  # setup base URL to web service:
  #
  configur = ConfigParser()
  configur.read(config_file)
  baseurl = configur.get('client', 'webservice')

  #
  # make sure baseurl does not end with /, if so remove:
  #
  if len(baseurl) < 16:
    print("**ERROR: baseurl '", baseurl, "' is not nearly long enough...")
    sys.exit(0)

  if baseurl == "https://YOUR_GATEWAY_API.amazonaws.com":
    print("**ERROR: update config file with your gateway endpoint")
    sys.exit(0)

  if baseurl.startswith("http:"):
    print("**ERROR: your URL starts with 'http', it should start with 'https'")
    sys.exit(0)

  lastchar = baseurl[len(baseurl) - 1]
  if lastchar == "/":
    baseurl = baseurl[:-1]

  #
  # main processing loop:
  #
  cmd = prompt()

  while cmd != 0:
    #
    if cmd == 1:
      upload_file(baseurl)
    elif cmd == 2:
      get_status(baseurl)
    elif cmd == 3:
      upload_and_poll(baseurl)
    elif cmd == 4:
      translate(baseurl)  
    elif cmd == 5:
        pass
    #   download(baseurl)
    elif cmd == 6:
        pass
    #   upload_and_poll(baseurl)
    else:
      print("** Unknown command, try again...")
    #
    cmd = prompt()

  #
  # done
  #
  print()
  print('** done **')
  sys.exit(0)

except Exception as e:
  logging.error("**ERROR: main() failed:")
  logging.error(e)
  sys.exit(0)
