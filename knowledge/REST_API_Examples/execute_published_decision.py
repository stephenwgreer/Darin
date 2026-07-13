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

# Create the request body. The request body specifies the 
# input values required by the decision.
# Modify these key-value pairs for your decision.
# Include underscores if needed.

requestBody = '''
{
"inputs" : [ 
  {"name": "debtinc_", "value" : 37.1136},
  {"name": "delinq_", "value" : 0},
  {"name": "derog_", "value" : 4},
  {"name": "value_", "value" : 60850}
 ]
}
'''

# Define the content and accept types for the request header.
contentType = "application/json"
acceptType = "application/json"

# Specify the module ID of the published decision, for example,
# "evaluate_loans24_0".
moduleID = "module-ID"

# Define the request URL.
masModuleUrl = "/microanalyticScore/modules/" + moduleID
requestUrl = baseUrl1 + masModuleUrl + "/steps/execute"

# Execute the decision. 
masExecutionResponse = post(requestUrl, contentType, 
                       acceptType, accessToken1, requestBody) 

# Display the response.
print ("response=", masExecutionResponse, end='\n\n')
print ("response content=", "\n", 
       json.dumps(json.loads(masExecutionResponse.content), 
       indent=4), end='\n\n')  