<< Include code from "Define Basic Methods and Get an Access Token". >>
<< That code is required to successfully execute this example.       >>

########################################
# Identify the node type to update.
# Define the updates to the node type 
# and the node type's content.
########################################

# Specify the name of the node that you want to
# update. Substitute '%20' for any spaces in the
# name. For example
# nodeName = "Calculate%20sum"
nodeName = "myCustomNode"

# Define the updates that you want to apply 
# to the node type.
nodeTypeUpdates = {
    "name": "Calculate sum",
    "themeId": "DNT_THEME2"}

# Define the updates that you want to apply
# to the content of the node.
nodeContentUpdates = '''
{
    "staticContent": "package \\"${PACKAGE_NAME}\\" /inline;\\n \
        dcl double b;\\n \
        method execute(double a, double c, in_out double b);\\n \
           b=a+c;\\n \
        end;\\n \
     endpackage;"}
'''

# Convert JSON string to a Python dictionary.
nodeContentUpdates=json.loads(nodeContentUpdates)

########################################
# Get the filtered list of custom node types,
# and extract the ID of the node that is 
# being updated.
########################################

# Get the filtered list of custom node types.
acceptType = "application/vnd.sas.collection+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes?filter=eq(name,%27" + nodeName + "%27)"
getListResponse,responseHeaders = get(requestUrl, accessToken1, acceptType)

# Convert the response to a JSON object.
responseBodyJson = json.loads(getListResponse)

# Retrieve the node type ID.
nodeTypeId = responseBodyJson['items'][0]['id']
print('id = ', nodeTypeId)

########################################
# Update the node type definition.
########################################

# Get the node type definition.
acceptType = "application/vnd.sas.decision.node.type+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes/" + nodeTypeId
getNodeResponse,responseHeaders = get(requestUrl, accessToken1, acceptType)

# Extract the ETag value from the response header.
ETag = responseHeaders['ETag']
print('ETAG=', ETag)

# Convert the response to a JSON object.
responseBodyJson = json.loads(getNodeResponse)

# Apply the type updates to the type definition that
# was returned by the GET request The variable 
# responseBodyJson will contain updated type definition 
responseBodyJson.update(nodeTypeUpdates)

# Convert responseBodyJson to a string. This string
# is specified as the request body in the PUT request
# that updates the node type definition.
requestBody = json.dumps(responseBodyJson)

# Update the node type definition.
contentType = "application/vnd.sas.decision.node.type+json"
putResponse = put(requestUrl, contentType, acceptType, \
                  accessToken1, "If-Match", ETag, requestBody)
print(putResponse, end='\n\n')
print ("updated node type definition = ","\n", json.dumps(json.loads(putResponse.content), 
       indent=4), end='\n\n')

########################################
# Update the node content.
########################################

# Get the node type content.
acceptType = "application/vnd.sas.decision.node.type.content+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes/" + nodeTypeId +"/content"
getNodeResponse,responseHeaders = get(requestUrl, accessToken1, acceptType)

# Extract the ETag value from the response header.
ETag = responseHeaders['ETag']
print('ETAG=', ETag)

# Convert the response to a JSON object.
responseBodyJson = json.loads(getNodeResponse)

# Apply the updates to the content that was 
# returned by the GET request. The variable 
# responseBodyJson will contain updated node
# type content 
responseBodyJson.update(nodeContentUpdates)

# Convert responseBodyJson to a string. This string
# is specified as the request body in the PUT request
# that updates the node content.
requestBody = json.dumps(responseBodyJson)

# Update the node type content.
contentType = "application/vnd.sas.decision.node.type.content+json"
putResponse = put(requestUrl, contentType, acceptType, \
                  accessToken1, "If-Match", ETag, requestBody)
print(putResponse, end='\n\n')
print ("updated node content = ","\n", json.dumps(json.loads(putResponse.content), 
       indent=4), end='\n\n')