import asyncio
import json
import uuid
import os
from typing import Dict, List, Any
from pathlib import Path
import base64
import aiofiles
import aiohttp
from tools.generate_audio import generate_audio  # New Import
from tools.generate_image import generate_image  # New Import
import asyncio  # Make sure it has been imported

class ProductionAgent:
    """Create an Agent - responsible for generating scene images, voice, and animation"""
    
    def __init__(self, ollama_client):
        self.ollama_client = ollama_client
        self.model_name = "gemma3n:e4b"
        # self.model_name = "qwen3:4b"
        self.assets_dir = Path("assets")
        self.assets_dir.mkdir(exist_ok=True)
        
        # Create a subdirectory
        (self.assets_dir / "images").mkdir(exist_ok=True)
        (self.assets_dir / "audios").mkdir(exist_ok=True)
        (self.assets_dir / "animations").mkdir(exist_ok=True)
    
    async def generate_assets(self, scene_design: Dict[str, Any]) -> Dict[str, Any]:
        """Generate all assets for the scene"""
        
        scene_id = scene_design.get("scene_id", f"scene_{uuid.uuid4().hex[:8]}")
        
        # Generate various materials in parallel
        image_task = sel生成各种素材f._generate_scene_image(scene_design)
        audio_task = self._generate_scene_audio(scene_design)
        animation_task = self._generate_animation_code(scene_design)
        
        # Wait for all tasks to complete
        image_url, audio_info, animation_code = await asyncio.gather(
            image_task, audio_task, animation_task
        )
        
        return {
            "scene_id": scene_id,
            "image_url": image_url,
            "audio_url": audio_info["url"],       # Audio Path
            "audio_duration": audio_info["duration"],  # New: Audio duration (seconds)
            "audio_script": scene_design.get("visual_description", ""), 
            "animation_code": animation_code,
            "assets_generated": True
        }
    
    async def _generate_scene_image(self, scene_design: Dict[str, Any]) -> str:
        """生成场景图片"""
        try:
            # Image generation APIs (such as DALL-E, Stable Diffusion, etc.) should be called here
            # For demonstration purposes, we use placeholder images.
            
            scene_id = scene_design.get("scene_id", "default")
            visual_description = scene_design.get("visual_description", "A beautiful scene with mountains and river")
            image_prompt = scene_design.get("image_prompt", "a beautiful girl standing in the forest")
            output_dir = self.assets_dir / "images"  # Use the created audio directory
            # Generate image descriptions using Ollama (if supported)
            # In actual applications, a dedicated image generation API should be called
            
            # Temporarily use placeholder images
            # placeholder_url = await self._get_placeholder_image(scene_id, image_prompt)
            
            # return placeholder_url
            print(f"visual_description: {visual_description}")
            print(f"image_prompt: {image_prompt}")

            image_url = await asyncio.to_thread(
                generate_image,
                prompt=image_prompt,
                scene_id=scene_id,
                output_dir=output_dir
            )
            
            # If the build fails, it returns the default placeholder.
            return image_url or "https://via.placeholder.com/800x600/4A90E2/FFFFFF?text=Scene+Image"
            
            
        except Exception as e:
            print(f"Image generation failed: {e}")
            return "https://via.placeholder.com/800x600/4A90E2/FFFFFF?text=Scene+Image"
    
    async def _get_placeholder_image(self, scene_id: str, prompt: str) -> str:
        """Get the placeholder image"""
        # Choose appropriate placeholders based on scene content
        if "forest" in prompt.lower() or "nature" in prompt.lower():
            return "https://images.pexels.com/photos/147411/italy-mountains-dawn-daybreak-147411.jpeg?auto=compress&cs=tinysrgb&w=800"
        elif "city" in prompt.lower() or "urban" in prompt.lower():
            return "https://images.pexels.com/photos/374870/pexels-photo-374870.jpeg?auto=compress&cs=tinysrgb&w=800"
        elif "ocean" in prompt.lower() or "sea" in prompt.lower():
            return "https://images.pexels.com/photos/1704488/pexels-photo-1704488.jpeg?auto=compress&cs=tinysrgb&w=800"
        elif "mountain" in prompt.lower():
            return "https://images.pexels.com/photos/1366919/pexels-photo-1366919.jpeg?auto=compress&cs=tinysrgb&w=800"
        else:
            return "https://images.pexels.com/photos/531880/pexels-photo-531880.jpeg?auto=compress&cs=tinysrgb&w=800"
    
    async def _generate_scene_audio(self, scene_design: Dict[str, Any]) -> str:
        """Generate scene speech (return a dictionary containing URL and duration)"""
        try:
            # dialogue_text = scene_design.get("dialogue_text", "")
            dialogue_text = scene_design.get("visual_description", "")
            
            if not dialogue_text:
                return {"url": "", "duration": 0}
            
            scene_id = scene_design.get("scene_id", "default")
            audio_output_dir = self.assets_dir / "audios"

            # Call the tool to generate speech (return a dictionary containing url and duration)
            audio_info = generate_audio(
                text=dialogue_text,
                scene_id=scene_id,
                output_dir=audio_output_dir
            )

            return audio_info if audio_info else {"url": "", "duration": 0}
        except Exception as e:
            print(f"Speech generation failed: {e}")
            return {"url": "", "duration": 0}
    
    async def _generate_animation_code(self, scene_design: Dict[str, Any]) -> str:
        """Generate animation code"""
        try:
            # Get animation information in scene design
            css_animation = scene_design.get("css_animation", "")
            animation_effects = scene_design.get("animation_effects", "")
            scene_id = scene_design.get("scene_id", "default")
            
            if css_animation:
                return css_animation
            
            # Generate animation code using AI
            prompt = f"""
As a front-end development expert, please create CSS animation code for the following scenarios：

ScenarioID: {scene_id}
animation effects: {animation_effects}
mood: {scene_design.get('mood', 'neutral')}
color: {scene_design.get('color_palette', [])}

Please create a complete CSS animation, including:
1. @keyframes definition
2. Animation class name
3. Transition effect
4. Appropriate animation duration

Requirements:
- The animation should be smooth and natural
- Suitable for web display
- Not too complex
- Ensure compatibility

Please return only the CSS code; do not include any other text.
"""
            
            response = await self.ollama_client.generate(
                model=self.model_name,
                prompt=prompt,
                stream=False
            )
            
            animation_code = response.get("response", "").strip()
            
            #If AI spawn fails, use default animation
            if not animation_code or len(animation_code) < 50:
                animation_code = self._create_default_animation(scene_id)
            
            return animation_code
            
        except Exception as e:
            print(f"Animation generation failed: {e}")
            return self._create_default_animation(scene_design.get("scene_id", "default"))
    
    def _create_default_animation(self, scene_id: str) -> str:
        """Creating a Default Animation"""
        return f"""
        @keyframes sceneAnimation_{scene_id} {{
            0% {{
                opacity: 0;
                transform: translateY(30px) scale(0.95);
            }}
            50% {{
                opacity: 0.7;
                transform: translateY(-5px) scale(1.02);
            }}
            100% {{
                opacity: 1;
                transform: translateY(0) scale(1);
            }}
        }}
        
        @keyframes backgroundPulse_{scene_id} {{
            0%, 100% {{
                background-size: 100% 100%;
            }}
            50% {{
                background-size: 110% 110%;
            }}
        }}
        
        .scene-animation {{
            animation: sceneAnimation_{scene_id} 3s ease-out forwards,
                      backgroundPulse_{scene_id} 6s ease-in-out infinite;
        }}
        
        .scene-animation::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(45deg, rgba(255,255,255,0.1), rgba(255,255,255,0));
            animation: shimmer_{scene_id} 4s ease-in-out infinite;
        }}
        
        @keyframes shimmer_{scene_id} {{
            0% {{
                transform: translateX(-100%);
            }}
            100% {{
                transform: translateX(100%);
            }}
        }}
        """