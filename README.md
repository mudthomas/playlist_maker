# Crown claimer
A playlist generator using the APIs of Spotify and last.fm.

## Background
Discord is a communications platform where people with similar intrests meet on servers. Some of these servers make use of different bots for fun or utility.

I frequent music oriented servers where a last.fm bot is used. When a user has logged the most plays of an artist they are rewarded a crown (i.e. fake internet point). Usually a lower limit is set for when a crown is to be awarded, the default is 30 plays.

Since I am Swedish I am naturally adept at competing in music instead of enjoying it. For more information on this, see Eurovision Song Contest.
Furthermore, Swedes do not just compete in music, we win. For more information on this, see ABBA.

Of course, cheating is not an option. So instead of just scrobbling songs in order to win, I need to listen to them. I first did this manually, that is looking at my last.fm account and then just playing the relevant artists on Spotify. However, this takes time management. Also, sometimes it leads to me "over-listening" an artist, e.g. getting 55 plays instead of stopping at 30.


## The code

This little Python script uses the last.fm API to find a users most played artists with less than 30 plays.
Then the Spotify API is used to find the top songs of those artist and adds them to a playlist.

A playlist is also generated to overtake the last.fm users in 'opponent_list.txt'. This file should have one username per line.

I have also added functionality to increase own plays to specific targets. I did this in order to push certain artists off of my top 100.

#### NOTE: User passwords and API keys are stored as plain text in auth.json. If you do not like this, there is a possibility to not save credentials after the session. I have no idea if this can be read from memory by some other malicious program.

For API accounts for last.fm and Spotify, see the following links:
* last.fm: https://www.last.fm/api
* Spotify: https://developer.spotify.com/documentation/web-api

Also a 'blacklist_artists.txt' can be added with one artist per line. These artists will not be added to playlists.

## The issues

The code is not fool proof. Here are the issues I have noticed, and will probably ignore.
* Code now takes the first 50 results and only proceeds if the last.fm and Spotify artists are equal. Issues still exists for multiple artists of same name.
* Songs are now only added if the wanted artist is the 'main' artist. This can result in no songs being added if the top ten are all songs featuring the wanted artist.
* At this time, Pylast has not implemented the last.fm API way of fetching more than 1000 top artist. As a workaround this code includes an extension of the pylast.User class, where this is implemented. A pull request might be sent to Pylast.

## The future

* As the opponent scrobbles are saved now, they could be popped if user is leading, saving cycles on later uses.
* Change the hardcoded Sleep times into an adaptive sleep from 429-errors.
* Add sanity checks. e.g. for values of scrobble target.
* I have noticed a lot of bands with names in non-latin scrips failing. I should look over my slapped-together filters (and alt-names) so they don't fail these without reason.
* Save more runtime information to save on calls. For example, what startpage to use for lastfm API, how many days since last lastfm pull (for reusing data, especially for opponent scrobbles)
* Add check for own user in opponent list, just as a safety deal.
* Using the code through executable, I have realized that a settings.txt would be nice.
* The code can be a bit touchy with bad connection, atm it kills the code. I should apply some loops together with try-excepts.
* Generate logs
* Add songs in order of 'plays found' not 'plays wanted'. This would make artists with fewer available songs move up.
* Possibility of adding albums instead of songs?
* Perhaps I will look into incorporating Discord API in order to send commands to the bot. For now I make use of the crownseeder admin command.
* It would be cool to include the weight of different opponents. Since for example, stealing the crown of the person just below you is better than the very last person. Also, I have not considered that the user might not actually be number one already, silly me. Stealing from people above you would clearly be more advantageous.
