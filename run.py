#!/usr/bin/env python3

import asyncio
import uvicorn
import sys
from pathlib import Path

#Add the current directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

async def check_ollama_connection():
    """Check Ollama Connection"""
    from utils.ollama_client import OllamaClient
    
    print("Check Ollama Connection...")
    try:
        async with OllamaClient() as client:
            models = await client.list_models()
            print(f"✓ Ollama connection successful, available models: {len(models.get('models', []))} ")
            
            # Check if there is gemma3n:e4b model
            if not await client.check_model_exists("gemma3n:e4b"):
                print("⚠️  Warning: gemma3n:e4b model not found")
                print("   Please run: ollama pull gemma3n:e4b")
            else:
                print("✓ gemma3n:e4b Model is ready")
                
    except Exception as e:
        print(f"✗ Ollama connection failed: {e}")
        print("Please make sure that the Ollama service is started and running 'ollama serve'")
        return False
    
    return True

def main():
    """Main function"""
    print("Launch novel animation interactive display system...")
    
    # Check Ollama Connection
    if not asyncio.run(check_ollama_connection()):
        print("Please start the Ollama service before running this program")
        return
    
    print("Start the web server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()