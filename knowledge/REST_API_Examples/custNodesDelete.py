<< Include code from "Define Basic Methods and Get an Access Token". >>
<< That code is required to successfully execute this example.       >>

# Define the DELETE function. This function defines the 
# request headers, submits the request, and returns the 
# response.

def delete(url1, accessToken):
    headers = {"Authorization": "bearer " + accessToken}
    req = sess.delete(url1, headers=headers)
    return req;

# Specify the name of the node that you want to
# delete. Substitute '%20' for any spaces in the
# name. For example
# nodeName = "Calculate%20sum"
nodeName = "Calculate%20sum"

# Get the filtered list of custom node types.
acceptType = "application/vnd.sas.collection+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes?filter=eq(name,%27" + nodeName + "%27)"
getListResponse,responseHeaders = get(requestUrl, accessToken1, acceptType)

# Convert the response to a JSON object.
responseBodyJson = json.loads(getListResponse)

# Retrieve the node type ID.
nodeTypeId = responseBodyJson['items'][0]['id']

# Define the request URL, and call the 
# DELETE function.

requestUrl = baseUrl1 + "/decisions/decisionNodeTypes/" + nodeTypeId
deleteResp = delete(requestUrl,accessToken1)
print ("delete response = ", deleteResp, end='\n\n')