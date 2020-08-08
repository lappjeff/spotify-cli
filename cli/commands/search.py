import click

from cli.utils import Spotify
from cli.utils.parsers import *
from cli.utils.functions import cut_string
from cli.utils.exceptions import *


@click.command(options_metavar='[<options>]')
@click.option(
    '--track', 'search_type', flag_value='track', default=True,
    help='(default) Search for a track.'
)
@click.option(
    '--album', 'search_type', flag_value='album',
    help='Search for an album'
)
@click.option(
    '--artist', 'search_type', flag_value='artist',
    help='Search for an artist.'
)
@click.option(
    '--playlist', 'search_type', flag_value='playlist',
    help='Search for a playlist'
)
@click.option(
    '-l', '--limit', type=int, default=10,
    help='Number of items to show.'
)
@click.option(
    '-v', '--verbose', count=True,
    help='Output more info (repeatable flag).'
)
@click.option(
    '--raw', is_flag=True,
    help='Output raw API response.'
)
@click.argument(
    'keyword', type=str, metavar='<keyword>'
)
def search(keyword, search_type='all', verbose=0, raw=False, limit=10, _return_parsed=False):
    """Search for any Spotify content."""
    import urllib.parse as ul
    from tabulate import tabulate

    pager = Spotify.Pager(
        'search',
        limit=limit,
        params={
            'q': ul.quote_plus(keyword),
            'type': search_type,
        },
        content_callback=lambda c: c[search_type+'s'],
    )
    if raw:
        if verbose >= 0:
            import json
            click.echo(json.dumps(pager.content))
        
        return pager.content


    def _get_conf_msg(cmd, search_type, indices_str):
        mapping = {
            'p': {
                'track': 'Play the selected track/s? ({})'.format(indices_str),
                'album': 'Play the selected album? ({})'.format(indices_str.split(',')[0]),
            },
            'q': {
                'track': 'Queue the selected track/s? ({})'.format(indices_str),
                'album': 'Queue the selected album? ({})'.format(indices_str.split(',')[0]),
            }
        }
        return mapping[cmd][search_type]


    if search_type == 'track':
        headers = ['Track', 'Artist']
        def _parse(item, index):
            item = parse_track_item_full(item)
            return {
                'Track': cut_string(item['track']['name'], 50),
                'Artist': cut_string(', '.join(item['artists']['names']), 30),
                'uri': item['track']['uri'],
                '#': index,
                'context_uri': item['album']['uri'],
                'track_number': item['track']['track_number'],
            }

        def _format_play_req(selected):
            if len(selected) == 1:
                return {
                    'context_uri': selected[0]['context_uri'],
                    'offset': {
                        'uri': selected[0]['uri'],
                    },
                }
            else:
                return {
                    'uris': [track['uri'] for track in selected],
                }

        def _format_queue_reqs(selected):
            return [
                {
                    'endpoint': 'me/player/queue?uri=' + s['uri'],
                    'method': 'POST',
                }
                for s in selected
            ]

    elif search_type == 'album':
        headers = ['Album', 'Artist']
        def _parse(item, index):
            return {
                'Album': cut_string(item['name'], 50),
                'Artist': cut_string(', '.join([a['name'] for a in item['artists']]), 30),
                'uri': item['uri'],
                '#': index,
                'id': item['id'],
            }

        def _format_play_req(selected):
            return {
                'context_uri': selected[0]['uri']
            }
        
        def _format_queue_reqs(selected):
            album = Spotify.request('albums/' + selected[0]['id'])
            return [
                {
                    'endpoint': 'me/player/queue?uri=' + track['uri'],
                    'method': 'POST',
                }
                for track in album['tracks']['items']
            ]

    else:
        raise FeatureInDevelopment
        

    headers.insert(0, '#')
    click.echo(
        '\nSearch results for "{}"'
        .format(keyword, int(pager.offset / pager.limit) + 1)
    )
    parsed_content = {}
    end_search = False
    while not end_search:
        table = []
        for i, item in enumerate(pager.content['items']):
            index = pager.offset + 1 + i
            parsed_item = _parse(item, index)
            parsed_content[index] = parsed_item
            row = [parsed_item[h] for h in headers]
            table.append(row)

        if len(table) == 0:
            click.echo('No data available for your search query.', err=True)
            return

        click.echo('\n', nl=False)
        click.echo(tabulate(table, headers=headers))
        response = click.prompt(
            '\nActions:\n'
            '[n]ext/[b]ack\n'
            '[p]lay/[q]ueue/[s]ave #[,...]\n'
            '[a]dd to playlist #[,...] <playlist>\n'
        ).lower()

        cmd = response.split(' ')[0]
        if cmd == 'n':
            try:
                pager.next()
            except PagerLimitReached:
                click.echo('\nThere are no more results to display.')
                continue

        elif cmd == 'b':
            try:
                pager.previous()
            except PagerPreviousUnavailable:
                click.echo('\nYou are already at the first page.')
                continue
        else:
            # parse selection
            try:
                indices_str = response.split(' ')[1]
            except IndexError:
                click.echo('\nInput error! Please try again.', err=True)
                continue

            indices = indices_str.split(',')
            selected = []
            for i in indices:
                try:
                    selected.append(parsed_content[int(i)])
                except:
                    continue

            # parse command
            click.echo('\n', nl=False)
            if len(selected) == 0:
                click.echo('\nInput error! Please try again.', err=True)
                continue

            conf = click.confirm(
                _get_conf_msg(cmd, search_type, indices_str),
                default=True
            )
            if not conf:
                pass

            elif cmd == 'p':
                from cli.commands.play import play
                req_data = _format_play_req(selected)
                play.callback(data=req_data, wait=0.2)

            elif cmd == 'q':
                requests = _format_queue_reqs(selected)
                Spotify.multirequest(requests, delay_between=0.1)
                click.echo('{} {}/s queued.'.format(len(selected), search_type))

            else:
                raise FeatureInDevelopment

            end_search = not click.confirm('\nContinue searching?', default=True)


    return

