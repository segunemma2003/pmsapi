from functools import wraps
from django.http import JsonResponse
import traceback
import openai

def handle_ai_errors(func):
    """Decorator to handle AI-related errors gracefully"""
    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        try:
            return func(self, request, *args, **kwargs)
        except openai.APIConnectionError:
            logger.error("OpenAI API connection error")
            return JsonResponse({
                'error': 'AI service temporarily unavailable. Please try again.',
                'fallback': True
            }, status=503)
        except openai.RateLimitError:
            logger.error("OpenAI rate limit exceeded")
            return JsonResponse({
                'error': 'AI service rate limit exceeded. Please wait a moment.',
                'fallback': True
            }, status=429)
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return JsonResponse({
                'error': 'AI service error. Please try again.',
                'fallback': True
            }, status=500)
        except Exception as e:
            logger.error(f"Unexpected error in AI extraction: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'error': 'An unexpected error occurred. Please try again.',
                'fallback': True
            }, status=500)
    return wrapper
