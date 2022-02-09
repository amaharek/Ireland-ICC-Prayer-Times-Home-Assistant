# Hass.io Custom Component - Remote Speaker
This custom component is the API component that adds a media player which interact with 
my custom local media player add-on [Remote Speaker](https://github.com/modestpharaoh/hassio-addons/tree/master/remote_speaker).

## Install
* Copy the 
tts_remote_speaker directory into the custom_components directory of home assistant.
* Reboot your Home assistant.
* You can add remote speaker media player, by the following config in the main config:
  ```
  media_player:
    - platform: tts_remote_speaker
      name: Hass Local Speaker
      address: http://192.168.x.x:5005 # The IP should be the hass.io local IP or docker container IP, port should be whatever configured for the addon (Default is 5005)
      volume: 0.8
      repeat_num_for_tts: 1
      announcement_music: false
  ```
* Reboot your home assistant, you should have media player entity: media_player.hass_local_speaker

## Supported Home Aassistant media player features:
* Home assistant local media browser.
* Play local media.
* Play certain media come with the containers such as alarm sounds and azan prayer.
* Play, pause, seek and stop current audio selected.
* Volume set.
* sources (The sources here are a predefined audios installed in the remote speaker addons)

### Extra features:
* Supports running announcement music before any running media, this controlled by announcement_music parameter.
* Supports repeating the audio for certain numbers, this controlled by repeat_num parameter.
* Supports media priority (0-100) for the current playing media, this controlled by priority parameter:
  * O is lowest priority and 100 is the highest.
  * If you are trying to play audio file with priority lower that the current playing media, it won't stop the current media.
  * If you are trying to play audio file with priority bigger or equal to the current playing media, it will the current media and play the new one.

## Custom Services
### play_audio
It allow you to play audio with the extra parameters (announcement_music, priority, repeat_num, volume)

```
tts_remote_speaker.play_audio:
    description: play audio with the extra parameters (announcement_music, priority, repeat_num, volume)
    fields:
        entity_id:
            description: Speaker Entity ID.
            example: 'media_player.tts_remote_speaker'
        media_id:
            description: Audio URL/Path/source for the audio file.
            example: 'alarm'
            example: '/media/audio_test.mp3'
            example: 'https://samplemusic.com/sample.mp3'
        volume:
            description: Volume level
            example: '0.2'
        announcement_music:
            description: To play the default announcement music or not.
            example: true
        repeat_num:
            description: Repeat playing of the audio file to that number.
            example: 2
        priority:
            description: Prioriy of the Media to play.
            example: 30
```
#### Media_id options
* If you add an URL, addons will download the file and play it.
* You can run any media /media/dwsdsad/xcxcx.mp3, it will play the local media file, as this supposed to be shared to the remote speaker addos
* Play any of the predefined  audio sources by just write the source name

#### Tips
An example automation should run Azan audio with higher priority (ex.priority 35) than other audio you run manually (ex. priority 0).
```
data_template:
  announcement_music: false  # You don't want annmoncement music before Azan
  entity_id: media_player.tts_remote_speaker
  media_id:  الأذان
  priority: 35
  repeat_num: 0  # You don't want to repeat Azan
  volume: 0.5
service: tts_remote_speaker.play_audio
```


### update_attributes
update media player special attributes and volume level (They will always override, if homeassistant restart)
```
tts_remote_speaker.update_attributes:
    description: update media player special attributes and volume level (They will always override, if homeassistant restart)
    fields:
        entity_id:
            description: Speaker Entity ID.
            example: 'media_player.tts_remote_speaker'
        volume:
            description: Volume level
            example: '0.2'
        announcement_music:
            description: To play the default announcement music or not.
            example: true
        repeat_num:
            description: Repeat playing of the audio file to that number.
            example: 2
```

## Credits
* Developed by [modestpharaoh](https://github.com/modestpharaoh)
