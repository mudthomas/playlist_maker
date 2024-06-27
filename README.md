# Crown claimer
A playlist generator using the APIs of Spotify and last.fm.

## Background
Discord is a communications platform where people with similar intrests meet on servers. Some of these servers make use of different bots for fun or utility.

I frequent music oriented servers where a last.fm bot is used. When a user has logged the most plays of an artist they are rewarded a crown (i.e. fake internet point). Usually a lower limit is set for when a crown is to be awarded, the default is 30 plays.

Since I am Swedish I am naturally adept at competing in music, instead of enjoying it. For more information on this, see ABBA.

Of course, cheating is not an option. So instead of just scrobbling songs in order to win, I need to listen to them. I first did this manually, that is looking at my last.fm account and then just playing the relevant artists on Spotify. However, this takes time management. Also, sometimes it leads to me "over-listening" an artist, e.g. getting 55 plays instead of stopping at 30.


## The code

This little Python script uses the last.fm API to find a users most played artists with less than 30 plays.
Then the Spotify API is used to find the top songs of those artist and adds them to a playlist.

A playlist is also generated to overtake the last.fm users in 'opponent_list.txt'.

I have also added functionality to increase own plays to specific targets. I did this in order to push certain artists off of my top 100.

NOTE: User passwords and API keys are stored as plain text in auth.json. If you do not like this, do not use it. In the future an alternative method might be added, but this suits me.


## The issues

The code is not fool proof. Here are the issues I have noticed, and will probably ignore.
* A search of the artist name supplied from last.fm is done on the Spotify API. The assumption is made that the first result is the correct artist. This is not always true. The code is verbose to be able to double check this.
* There is sometimes discrepancies between the attribution done by Spotify and last.fm. This can result in the wrong artist being added to the playlist.
* Pylast has not implemented the last.fm API way of fetching more than 1000 artist. When I have surpassed this limit myself I might consider a work around. I read on somewhere that there is no limit on the "recent plays".

## The future

* I might make an executable to let other, jealous users make use of it.
* A prompt to populate auth.json when it does not exist would be nice.
* Perhaps I will look into incorporating Discord API in order to send commands to the bot. For now I make use of the crownseeder admin command.
