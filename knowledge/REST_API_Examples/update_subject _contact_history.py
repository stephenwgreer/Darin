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

# Specify the tracking code for the subject contact record, 
# and the object ID of the treatment that you want to update.
# Both values are GUIDs such as 
# "b48ac290-f1a5-7343-8d85-e6f9fc85ff23".
trackingCode = "tracking-code"
treatmentToUpdate = "treatment-ID"

# Specify record-level updates. Modify these values 
# values for your application.
recordUpdates = {"conclusionResponseValue" : "accepted", 
                 "conclusionResponseType" : "crt_x"}

# Specify the updates that you want to make to the 
# the treatment in the subject contact record. 
# Modify these values for your application.
treatmentUpdates = {"presented" : "True", 
                    "presentedTimeStamp" : "2019-11-14T18:47:40.719Z",
                    "responseValue" : "accepted", 
                    "responseChannel" : "Web",
                    "respondedTimeStamp" : "2019-11-15T21:09:32.059Z"}
        
# Get the subject contact record for the tracking code.
requestUrl = baseUrl1 + \
    "/subjectContacts/contacts?filter=eq(responseTrackingCode,'" + \
    trackingCode +"')"
acceptType = "application/vnd.sas.collection+json"
respBodyTC,respHeaders = get(requestUrl, accessToken1, acceptType)

print ("response body = ", "\n", json.dumps(json.loads(respBodyTC), 
       indent=4), end='\n\n')

# Convert the response to a JSON object, and 
# extract the object ID.
respStrTC = json.loads(respBodyTC)
objID = respStrTC['items'][0]['id']

# Get the subject contact record using the object ID.
# The header returned by this request includes the 
# ETag value that you need to update the record.
acceptType = "application/vnd.sas.decision.subject.contact+json"
requestUrl = baseUrl1 + "/subjectContacts/contacts/" + objID
respBodyOBJ,respHeaders = get(requestUrl, accessToken1, acceptType)

# Convert the response to a JSON object, and 
# extract the ETag value. 
respBodyObjJSON = json.loads(respBodyOBJ)
ETag = respHeaders['ETag']

# The variable respBodyObjJSON will contain all of the updates 
# that need to be added to the subject contact record.
# Add the conclusionRepsonseValue and conclusionResponseType 
# to the updates.
respBodyObjJSON.update(recordUpdates)

# For each treatment in the record, add the treatment data to 
# the object respBodyObjJSON. For the treatment that is being 
# updated, append the updates. 
treatmentList=[]
for item in respBodyObjJSON['treatmentsForConsideration']:
    if item['id'] == treatmentToUpdate:
        item.update(treatmentUpdates)
    treatmentList.append(item)
contactUpdate = {"treatmentsForConsideration" : treatmentList}
respBodyObjJSON.update(contactUpdate)
 
# Convert the updated object to a string.
requestBody = json.dumps(respBodyObjJSON)

#Update the subject contact history record.
contentType = "application/vnd.sas.decision.subject.contact+json"
putResponse = put(requestUrl, contentType, acceptType, \
                  accessToken1, "If-Match", ETag, requestBody)
print(putResponse, end='\n\n')
print ("putResponse = ","\n", json.dumps(json.loads(putResponse.content), 
       indent=4), end='\n\n')