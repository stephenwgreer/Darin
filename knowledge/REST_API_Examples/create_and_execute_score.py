import sys, json
import urllib.parse as u1
import urllib.request as urllib2
import urllib.error as urllib3
import base64
import pprint
import requests
import re as regexp
import datetime
from time import sleep

# The GETACCESSTOKEN function requests an access token using the SAS Logon 
# OAuth API. The response contains a field named access_token that contains 
# the value of the token that you use for subsequent API requests.

def getAccessToken(baseUrl1):
    url1 = baseUrl1 + '/SASLogon/oauth/token'
    
    # Replace client-ID and client-secret
    # with values appropriate for your environment. 
    s = "client-ID:client-secret"
    
    # Encode the value of the client ID.
    tokenCredentials = base64.b64encode(s.encode('ascii')).decode('ascii')
    headers = {"Accept": "application/json",
               "Authorization": "Basic " + tokenCredentials,
               "Content-Type": "application/x-www-form-urlencoded" }
    values = { "grant_type": "password",
               "username": userid,
               
               "password": password }
    # Convert the values dictionary into a string.
    dV = u1.urlencode(values)
    dV = dV.encode('ascii')
    
    # Request an access token.
    req = urllib2.Request(url1, data=dV, headers=headers)
    try:
        # Open the response object, and convert it into a Python object.
        responseLogon = urllib2.urlopen(req)
        body = responseLogon.read()
        responseBodyJson = json.loads(body)
        
        # Extract the access token from the response.
        accessToken1 = responseBodyJson['access_token']
    except urllib3.URLError as e:
        if hasattr(e, 'reason'):
            print ('Failed to reach a server.')
            print ('Error: ', e.reason)
            print (e)
        elif hasattr(e, 'code'):
            print ('The server could not fulfill the request.')
            print ('Error: ', e.reason)
    except urllib3.HTTPError as e:
        print ('Error: ', e.reason)
    return accessToken1;

# Define the GET function. This function defines request headers, 
# submits the request, and returns both the response body and
# the response header.

def get(url1, accessToken1, accept):
    headers = {"Accept": accept,
               "Authorization": "bearer " + accessToken1}
    try:
        # Submit the request.
        req = urllib2.Request(url1, headers=headers)
        
        # Open the response, and convert it to a string.
        domainsResponse = urllib2.urlopen(req)    
        body = domainsResponse.read()
        
        # Return the response body and the response headers.
        respHeaders = domainsResponse.headers
        return body, respHeaders
    except urllib3.URLError as e:
        if hasattr(e, 'reason'):
            print ('Failed to reach a server.')
            print ('Error: ', e.read())
        elif hasattr(e, 'code'):
            print ('The server could not fulfill the request.')
            print ('Error: ', e.read())
    except urllib3.HTTPError as e:
        print ('Error: ', e.read())


# Define the POST function. This function converts the request body into
# a JSON object, defines the request headers, posts the request, and 
# returns the response.

def post(url1, contentType, accept, accessToken, body):
    headers = {"Accept": accept,
               "Authorization": "bearer " + accessToken,
               "Content-Type": contentType }
    
    # Convert the request body to a Python object.
    reqBody = json.loads(body)
    
    # Post the request.
    req = sess.post(url1, json=reqBody, headers=headers)
    return req;

# Define the PUT function. This function converts the request body into
# a JSON object, defines the request headers, and submits the request.
# The conditionalPutKey and conditionalPutValue fields are used to 
# identify a specific state of the resource. See "Updating Objects with 
# The put() Function".

def put(url1, contentType, accept, accessToken, conditionalPutKey, conditionalPutValue, body):
    headers = {"Accept": accept,
               "Authorization": "bearer " + accessToken,
               "Content-Type": contentType,
               conditionalPutKey : conditionalPutValue } 
    if (contentType != "text/plain"):
        reqBody = json.loads(body)
        res = sess.put(url1, json=reqBody, headers=headers)
    else:
        res = sess.put(url1, body, headers=headers)
    return res

# Specify the URL, user ID, and password required to access your server.
baseUrl1 = 'http://host.com'
userid = 'user-ID'
password = 'password'

# Get an access token.
accessToken1 = getAccessToken(baseUrl1);

# Create a session object.
sess = requests.Session()

# Specify the ID of the decision that you want to test, for example,
# "e289b21b-4be1-4739-9313-639b9629cb42".
decision_ID = "decision-ID"

# Define the URI to the decision object.
objectUri = "/decisions/flows/" + decision_ID

# Define the request body for the score definition.
# Modify these values to match the data for your test.

scoreDefinitionBody = '''
   {
      "name": "test_name",
      "objectDescriptor": 
         {
         "name":"decision_name",
         "type": "decision",
         "uri": "%s"
         },
      "inputData": 
         {
            "type": "CASTable",
            "tableName": "HMEQ_TRAIN",
            "libraryName": "Public",
            "serverName": "cas-shared-default"         
         },
      "mappings": [
         {
            "variableName": "value",
            "mappingType": "datasource",
            "mappingValue": "value"
         },
         {
            "variableName": "debtinc",
            "mappingType": "datasource",
            "mappingValue": "debtinc"
         },
         {
            "variableName": "derog",
            "mappingType": "datasource",
            "mappingValue": "derog"
         },
         {
            "variableName": "delinq",
            "mappingType": "datasource",
            "mappingValue": "delinq"
         }
      ],
      "properties": {
         "outputServerName": "cas-shared-default",
         "outputLibraryName": "Public",
         "tableBaseName": "decisionTest_results"
      }
}
''' %(objectUri)

# Create the score definition.
requestUrl= baseUrl1 + "/scoreDefinitions/definitions"
scoreCreationResponse = post(requestUrl, 
                        "application/vnd.sas.score.definition+json", 
                        "application/vnd.sas.score.definition+json",  
                        accessToken1, scoreDefinitionBody);
print ("creation response=", scoreCreationResponse, end='\n\n')
print ("creation response content=", "\n", 
       json.dumps(json.loads(scoreCreationResponse.content), 
       indent=4), end='\n\n')                         

# Retrieve the ID of the score definition from the response.
responseObject=scoreCreationResponse.json()
scoreDefinitionID = responseObject['id']

# Create the request body for executing the score defintion.
# The request name is a descriptive name that is displayed  
# when you view the log of API calls on your network.
scoreExecutionBody = '''
   {
      "name": "request-name",
      "scoreDefinitionId": "%s",
      "hints": {
         "inputLibraryName": "Public",
         "inputTableName": "HMEQ_TRAIN",
         "objectURI": "%s"
      }
}
''' %(scoreDefinitionID, objectUri)

# Execute the score code. (Create a score execution.)
requestUrl= baseUrl1 + "/scoreExecution/executions"
scoreExecutionResponse =  post(requestUrl, 
                               "application/vnd.sas.score.execution.request+json", 
                               "application/vnd.sas.score.execution+json",  
                               accessToken1, scoreExecutionBody);
                               
print ("execute response=", scoreCreationResponse, end='\n\n')

# Print the response body in readable format.
printable = json.loads(scoreExecutionResponse.content)
print("scoreExecutionResponse body = ", "\n", 
    json.dumps(printable, indent=4), end="\n\n")