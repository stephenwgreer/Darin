<< Include code from "Define Basic Methods and Get an Access Token". >>
<< That code is required to successfully execute this example.       >>

# Define the accept type and request URL to
# to get the list of custom node types.
acceptType = "application/vnd.sas.collection+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes"

# Submit the GET request for the node type list.
getListResponse,responseHeaders = get(requestUrl, accessToken1, acceptType)
responseBodyJson = json.loads(getListResponse)
print ("get list response content =", "\n", 
       json.dumps(responseBodyJson, 
       indent=4), end='\n\n')