<< Include code from "Define Basic Methods and Get an Access Token". >>
<< That code is required to successfully execute this example.       >>

##############################################
# Create a custom static node type definition 
# named myCustomNode.
##############################################

contentType = "application/vnd.sas.decision.node.type+json"
acceptType = "application/vnd.sas.decision.node.type+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes"

requestBody = '''
{
  "name": "myCustomNode",
  "hasProperties": true, 
  "hasInputs": true, 
  "hasOutputs": true,
  "inputDatagridMappable": false,
  "outputDatagridMappable": false,
  "inputDecisionTermMappable": true,
  "outputDecisionTermMappable": true,
  "type": "static",
  "description": "My custom node",
  "themeId": "DNT_THEME1"
}
'''
createResponse= post(requestUrl, contentType, acceptType, 
                     accessToken1, requestBody)
print ("create response = ", createResponse, end='\n\n')
print ("create response content =", "\n", 
       json.dumps(json.loads(createResponse.content), 
       indent=4), end='\n\n')

# Retrieve the ID of the node type from the response.

responseObject=createResponse.json()
nodeTypeID = responseObject['id']
print ("nodeTypeID=", nodeTypeID)


##############################################
# Define the DS2 content for the node type.
##############################################

# Define the DS2 code and the variables for the static node.

contentType = "application/vnd.sas.decision.node.type.content+json"
acceptType = "application/vnd.sas.decision.node.type.content+json"
requestUrl = baseUrl1 + "/decisions/decisionNodeTypes/" + nodeTypeID + "/content"

# Define the request body for the node content.
# See step 5b in the "How To" instructions for
# information on escape characters.

requestBody = '''
{
  "contentType": "DS2",
  "staticContent": "package \\"${PACKAGE_NAME}\\" /inline;\\n \
     dcl double b;\\n \
       method execute(double a, double c, in_out double b);\\n \
         b=a+c;\\n \
         put 'b=' b; \
       end;\\n \
     endpackage;",
  "nodeTypeSignatureTerms": [
    {
      "name": "a",
      "dataType": "decimal",
      "direction": "input"
    },
    {
      "name": "c",
      "dataType": "decimal",
      "direction": "input"
    },
    {
      "name": "b",
      "dataType": "decimal",
      "direction": "output"
    }
  ]
}
''' 

contentResponse= post(requestUrl, contentType, acceptType,
                     accessToken1, requestBody)
print ("content response = ", contentResponse, end='\n\n')
print ("content response content =", "\n", 
       json.dumps(json.loads(contentResponse.content), 
       indent=4), end='\n\n')