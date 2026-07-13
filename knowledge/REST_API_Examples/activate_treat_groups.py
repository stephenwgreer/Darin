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

# Get the treatment groups based on filter criteria.
# Modify the filter criteria as needed for your application.
requestUrl= baseUrl1 + \
    "/treatmentDefinitions/definitionGroups?filter=eq(name,'hmeq_Treatment_Group')"
responseObj,responseHeaders =  get(requestUrl, accessToken1, 
                               "application/vnd.sas.collection+json");
responseObj = json.loads(responseObj)

# Print the response body in readable format.
print ("responseObj = ", "\n", json.dumps(responseObj, 
       indent=4), end='\n\n')

# Define the treatment defintions URL and the accept type for requests.
acceptType = "application/vnd.sas.treatment.definition.group+json"
groupDefUrl = "/treatmentDefinitions/definitionGroups/"

# For each treatment group ID in the list...
for item in responseObj['items']:
    groupID = item['id']
    
    # Get the treatment group definition.
    requestUrl=baseUrl1 + groupDefUrl + groupID
    responseBody,responseHeaders = get(requestUrl, accessToken1, acceptType)
    responseBodyGrpJson = json.loads(responseBody)
    
    print ("group responseBody = ", "\n", json.dumps(responseBodyGrpJson, 
           indent=4), end='\n\n')
    print ("group responseHeaders = ", "\n", responseHeaders, end='\n\n')
    
    # Convert the treatment group definition to a string.
    # This string is passed as the request body when you create a
    # new revision of the treatment group.
    requestBody = responseBody.decode()
    
    # Lock the current version and create a new current version.
    requestUrl = baseUrl1 + groupDefUrl + groupID + "/revisions"
    responseObj = post(requestUrl, 
                      "application/vnd.sas.treatment.definition.group+json",
                      acceptType, accessToken1, requestBody)
    print ("new version response = ", responseObj)
    
    # Get the treatment group definition again and extract 
    # the new ETag value for the group.
    requestUrl=baseUrl1 + groupDefUrl + groupID
    responseBody,responseHeaders = get(requestUrl, accessToken1, acceptType)
    responseBodyGrpJson = json.loads(responseBody)
    groupEtag=responseHeaders['ETag']
       
    # Get the list of revisions for the treatment group with ID=groupID, 
    # sorted in descending order based on the major and minor revision numbers.
    # If your treatment group has more than 100 revisions, modify the limit
    # in the following URL.
    
    requestUrl=baseUrl1 + groupDefUrl + groupID + "/revisions" + \
      "?start=0&limit=100&sortBy=majorRevision:descending,minorRevision:descending"
    responseBody,responseHeaders = get(requestUrl, accessToken1, 
                                       "application/json")
    responseBodyJson = json.loads(responseBody)
    
    print("number of revisions = ", responseBodyJson['count'], end='\n\n')
    printable = json.dumps(responseBodyJson, indent=4)
    print("revision list responseBody = ", '\n\n', printable, end='\n\n')
    
    # Get the revision ID.
    revisionID=responseBodyJson['items'][1]['id']

    print ("Activating treatment group ", 
           responseBodyJson['items'][1]['name'], "\n",
           "Revision ", revisionID, end='\n\n')
            
    # Activate the locked revision of the treatment group.
    
    requestUrl=baseUrl1 + groupDefUrl + groupID + "/active"
    response = put(requestUrl,"text/plain", acceptType,
                  accessToken1, "If-Match", groupEtag, revisionID)
    print ("Activation response = ", response)