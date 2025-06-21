from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import json
import yt_dlp
import os
import assemblyai as aai
import openai
from .models import BlogPost

# Create your views here.
@login_required
def index(request):
    return render(request, 'index.html')

@csrf_exempt
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            yt_link = data['link']
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid data sent'}, status=400)


        # get yt title
        title = yt_title(yt_link)

        # get transcript
        transcription = get_transcription(yt_link)
        if not transcription:
            return JsonResponse({'error': " Failed to get transcript"}, status=500)


        # use OpenAI to generate the blog
        blog_content = generate_blog_from_transcription(transcription)
        if not blog_content:
            return JsonResponse({'error': " Failed to generate blog article"}, status=500)

        # save blog article to database
        new_blog_article = BlogPost.objects.create(
            user=request.user,
            youtube_title=title,
            youtube_link=yt_link,
            generated_content=blog_content,
        )
        new_blog_article.save()

        # return blog article as a response
        return JsonResponse({'content': blog_content})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def yt_title(link):
    """Retrieve video title using yt-dlp without downloading the video."""
    ydl_opts = {
        'quiet': True,
        'skip-download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(link, download=False)
    if info is None or 'title' not in info:
        raise Exception("Unable to retrieve video information.")
    return info['title']


def download_audio(link):
    """Download audio as an .mp3 file using yt-dlp."""
    ydl_opts = {
        'ffmpeg_location': "/usr/bin/ffmpeg",  # or omit if already in PATH
        'format': 'bestaudio/best',
        'quiet': True,
        # <- omit %(ext)s here
        'outtmpl': os.path.join(settings.MEDIA_ROOT, '%(id)s. %(title)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(link, download=True)

    if info is None or 'id' not in info or 'title' not in info:
        raise Exception("Unable to extract audio.")
    

    return os.path.join(settings.MEDIA_ROOT, f"{info['id']}. {info['title']}.mp3")




def get_transcription(link):
    audio_file = download_audio(link)
    aai.settings.api_key = os.environ['ASSEMBLY_AI_APKKEY']

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file)

    return transcript.text


client = openai.OpenAI(api_key=os.environ['OPEN_AI_APIKEY'])

def generate_blog_from_transcription(transcription):
    """
    Generates a blog post using the OpenAI GPT-3.5-turbo model based on a given transcription.

    Args:
        transcription (str): The text content from which to generate the blog post.

    Returns:
        str: The generated blog post content.
    """
    try:
        response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {"role": "user", "content": f"Write a blog post based on this transcription: {transcription}"}
            ],
            temperature=0.7,
        )
        # Accessing the content from the new API response structure
        # Added a check to ensure response.choices[0].message.content is not None
        if response.choices and response.choices[0].message and response.choices[0].message.content is not None:
            return response.choices[0].message.content.strip()
        else:
            return "Could not generate blog post: No content or empty content in response."
    except openai.APIError as e:
        # Handle API errors (e.g., invalid API key, rate limits)
        print(f"OpenAI API Error: {e}")
        return f"An error occurred while communicating with the OpenAI API: {e}"
    except Exception as e:
        # Handle other potential errors
        print(f"An unexpected error occurred: {e}")
        return f"An unexpected error occurred: {e}"


def blog_list(request):
    blog_articles = BlogPost.objects.filter(user=request.user)
    return render(request, "all_blogs.html", {'blog_articles': blog_articles})

def blog_details(request, pk):
    blog_article_detail = BlogPost.objects.get(id=pk)
    if request.user == blog_article_detail.user:
        return render(request, 'blog-details.html', {'blog_article_detail': blog_article_detail})
    else:
        return redirect('/')

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            error_message = "Invalid username or password"
            return render(request, 'login.html', {'error_message': error_message})
        
    return render(request, 'login.html')

def user_signup(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatPassword = request.POST['repeatPassword']

        if password == repeatPassword:
            try:
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except:
                error_message = 'Error creating account'
                return render(request, 'signup.html', {'error_message':error_message})
        else:
            error_message = 'Password do not match'
            return render(request, 'signup.html', {'error_message':error_message})
        
    return render(request, 'signup.html')

def user_logout(request):
    logout(request)
    return redirect('/')