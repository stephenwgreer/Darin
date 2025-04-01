import json

def process_with_anthropic(client, transcript_text, prompt_template):
    """Process transcript with Anthropic API and return response"""
        
    try:
        prompt = prompt_template.format(transcript=transcript_text)
        
        message = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1024,
            temperature=0,
            system="You analyze transcripts and extract key information.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract text from the response
        response_text = message.content[0].text
        
        # Try to parse as JSON if applicable
        try:
            json_result = json.loads(response_text)
            return json_result  # Return the parsed JSON as a dictionary
        except json.JSONDecodeError:
            # If not valid JSON, return the raw text
            return {"result": response_text}
                
    except Exception as e:
        return {"error": str(e)}

def process_with_template(client, transcript, template, **kwargs):
    """Process transcript with a specific template and return the result"""
    try:
        prompt = template.format(transcript=transcript, **kwargs)
        
        message = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1024,
            temperature=0,
            system="You analyze transcripts and extract key information.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
    except Exception as e:
        return {"error": str(e)}