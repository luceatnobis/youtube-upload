#!/usr/bin/env python3
#
# Upload videos to Youtube from the command-line using APIv3.
#
# Author: Arnau Sanchez <pyarnau@gmail.com>
# Project: https://github.com/tokland/youtube-upload
"""
Upload a video to Youtube from the command-line.

    $ youtube-upload --title="A.S. Mutter playing" \
                     --description="Anne Sophie Mutter plays Beethoven" \
                     --category=Music \
                     --tags="mutter, beethoven" \
                     anne_sophie_mutter.flv
    pxzZ-fYjeYs
"""

import os
import sys
import argparse
import collections
import webbrowser

import apiclient.errors
import oauth2client

import lib
import auth
import playlists
import categories
import upload_video
import yu_exceptions as ex

# http://code.google.com/p/python-progressbar (>= 2.3)
try:
    import progressbar
except ImportError:
    progressbar = None

EXIT_CODES = {
    ex.OptionsError: 2,
    ex.InvalidCategory: 3,
    ex.RequestError: 3,
    ex.AuthenticationError: 4,
    oauth2client.client.FlowExchangeError: 4,
    NotImplementedError: 5,
}

WATCH_VIDEO_URL = "https://www.youtube.com/watch?v={id}"

debug = lib.debug
struct = collections.namedtuple


def open_link(url):
    """Opens a URL link in the client's browser."""
    webbrowser.open(url)


def get_progress_info():
    """Return a function callback to update the progressbar."""
    progressinfo = struct("ProgressInfo", ["callback", "finish"])

    if progressbar:
        widgets = [
            progressbar.Percentage(), ' ',
            progressbar.Bar(), ' ',
            progressbar.ETA(), ' ',
            progressbar.FileTransferSpeed(),
        ]
        bar = progressbar.ProgressBar(widgets=widgets)

        def _callback(total_size, completed):
            if not hasattr(bar, "next_update"):
                bar.maxval = total_size
                bar.start()
            bar.update(completed)

        def _finish():
            if hasattr(bar, "next_update"):
                return bar.finish()
        return progressinfo(callback=_callback, finish=_finish)
    else:
        return progressinfo(callback=None, finish=lambda: True)


def get_category_id(category):
    """Return category ID from its name."""
    if category:
        if category in categories.IDS:
            ncategory = categories.IDS[category]
            debug("Using category: {0} (id={1})".format(category, ncategory))
            return str(categories.IDS[category])
        else:
            msg = "{0} is not a valid category".format(category)
            raise ex.InvalidCategory(msg)


def upload_youtube_video(youtube, options, video_path, total_videos, index):
    """Upload video with index (for split videos)."""
    u = lib.to_utf8
    title = u(options.title)
    if hasattr(u('string'), 'decode'):
        description = u(options.description or "").decode("string-escape")
    else:
        description = options.description
    if options.publish_at:
        debug("Your video will remain private until specified date.")

    tags = [u(s.strip()) for s in (options.tags or "").split(",")]
    ns = dict(title=title, n=index+1, total=total_videos)
    title_template = u(options.title_template)
    complete_title = (
        title_template.format(**ns) if total_videos > 1 else title)
    progress = get_progress_info()
    category_id = get_category_id(options.category)
    request_body = {
        "snippet": {
            "title": complete_title,
            "description": description,
            "categoryId": category_id,
            "tags": tags,
        },
        "status": {
            "privacyStatus": (
                "private" if options.publish_at else options.privacy),
            "publishAt": options.publish_at,

        },
        "recordingDetails": {
            "location": lib.string_to_dict(options.location),
        },
    }

    debug("Start upload: {0}".format(video_path))
    try:
        video_id = (
            upload_video.upload(youtube, video_path, request_body,
                                progress_callback=progress.callback))
    except apiclient.errors.HttpError as error:
        raise ex.RequestError(
            "Server response: {0}".format(error.content.strip()))
    finally:
        progress.finish()
    return video_id


def get_youtube_handler(options):
    """Return the API Youtube object."""
    home = os.path.expanduser("~")
    default_client_secrets = lib.get_first_existing_filename(
        [sys.prefix, os.path.join(sys.prefix, "local")],
        "share/youtube_upload/client_secrets.json")
    default_credentials = os.path.join(
        home, ".youtube-upload-credentials.json")
    client_secrets = options.client_secrets or default_client_secrets or \
        os.path.join(home, ".client_secrets.json")
    credentials = options.credentials_file or default_credentials
    debug("Using client secrets: {0}".format(client_secrets))
    debug("Using credentials file: {0}".format(credentials))
    get_code_callback = (
        auth.browser.get_code if options.auth_browser
        else auth.console.get_code
    )
    return auth.get_resource(
        client_secrets, credentials, get_code_callback=get_code_callback)


def parse_options_error(parser, options):
    """Check errors in options."""
    required_options = ["title"]
    missing = [opt for opt in required_options if not getattr(options, opt)]
    if missing:
        parser.print_usage()
        msg = (
            "Some required option are missing: {0}".format(", ".join(missing))
        )
        raise ex.OptionsError(msg)


def run_main(parser, options, args, output=sys.stdout):
    """Run the main scripts from the parsed options/args."""
    parse_options_error(parser, options)
    youtube = get_youtube_handler(options)

    if youtube:
        for index, video_path in enumerate(args):
            video_id = upload_youtube_video(
                youtube, options, video_path, len(args), index)
            video_url = WATCH_VIDEO_URL.format(id=video_id)
            debug("Video URL: {0}".format(video_url))
            if options.open_link:
                # Opens the Youtube Video's link in a webbrowser
                open_link(video_url)
            if options.thumb:
                youtube.thumbnails().set(
                    videoId=video_id, media_body=options.thumb).execute()
            if options.playlist:
                playlists.add_video_to_playlist(
                    youtube, video_id, title=options.playlist,
                    privacy=options.privacy
                )
            output.write(video_id + "\n")
    else:
        raise ex.AuthenticationError("Cannot get youtube resource")


def main(arguments):
    """Upload videos to Youtube."""
    usage = """Usage: %(prog)s [OPTIONS] VIDEO [VIDEO2 ...]

    Upload videos to Youtube."""
    parser = argparse.ArgumentParser(usage=usage)

    # Video metadata
    parser.add_argument("video_file", nargs=1)
    parser.add_argument(
        '-t', '--title', dest='title', help='Video title', required=True
    )
    parser.add_argument(
        '-c', '--category', dest='category', help='Video category'
    )
    parser.add_argument(
        '-d', '--description', dest='description',  help='Video description'
    )
    parser.add_argument(
        '--tags', dest='tags',
        help='Video tags (separated by commas: tag1, tag2,...'
    )
    parser.add_argument(
        '--privacy', dest='privacy', metavar="STRING", default="public",
        help='Privacy status (public | unlisted | private)'
    )
    parser.add_argument(
        '--publish-at', dest='publish_at', metavar="datetime", default=None,
        help='Publish Date: YYYY-MM-DDThh:mm:ss.sZ'
    )
    parser.add_argument(
        '--location', dest='location', default=None, help='Video location"',
        metavar="latitude=VAL,longitude=VAL[,altitude=VAL]"
    )
    parser.add_argument(
        '--thumbnail', dest='thumb', help='Video thumbnail'
    )
    parser.add_argument(
        '--playlist', dest='playlist',
        help='Playlist title (if it does not exist, it will be created)'
    )
    parser.add_argument(
        '--title-template', dest='title_template', metavar="STRING",
        default="{title} [{n}/{total}]",
        help='Template for multiple videos (default: {title} [{n}/{total}])'
    )

    # Authentication
    parser.add_argument(
        '--client-secrets', dest='client_secrets',
        help='Client secrets JSON file'
    )
    parser.add_argument(
        '--credentials-file', dest='credentials_file',
        help='Credentials JSON file'
    )
    parser.add_argument(
        '--auth-browser', dest='auth_browser', action='store_true',
        help='Open a GUI browser to authenticate if required'
    )

    #Additional options
    parser.add_argument(
        '--open-link', dest='open_link', action='store_true',
        help='Opens a url in a web browser to display uploaded videos'
    )

    args = parser.parse_args()
    # run_main(parser, options, args)
    run_main(parser, args, args.video_file)


def run():
    sys.exit(lib.catch_exceptions(EXIT_CODES, main, sys.argv[1:]))

if __name__ == '__main__':
    run()
