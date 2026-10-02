# Sloker - the CLI slop poker
This is a great way to play poker when you're bored at work. The program has a feature that lets you **switch to a regular terminal at any time without losing your progress in the game**. You can then check whatever you want or perform some tasks **to make it look like you're working**.

There are two game modes: **quick match** and **tournament**.

I probably don’t need to explain the quick match - you just start a game and then you’re playing.

The tournament has three stages - at each stage, before the game starts, **you can save your progress and return to it later**, even after shutting down your computer.

In the menu, you’ll also find options where you can set the number of bots (values between 1 and 7), the blinds, how often the blinds increase, and by how much.

This code is 100% **AI generated slop**. I just told it what I wanted this to look like and pasted in the error codes it was supposed to fix.

**I didn’t look too closely at the code** – I’d rather not know what kind of heresies are lurking in there. A project born out of boredom that turned into a real need - to keep myself from getting bored at work on a monitored network with lots of restrictions. You found this project, but you have GitHub blocked? Copy it over to Pastebin, put it on a USB drive, or if you’re a masochist, type it out from your phone - run it and enjoy.

# What will I need?
- At least 1 working limb
- Working computer (Windows or Linux)
- Python 3

# How to install and run:
- If you're on Windows: open terminal and type `wsl --install -d Debian` (you can choose any distro you like, I will use Debian here as an example)
- create user, password and whatever installer would ask you
- After restarting computer open WSL (Also if you have Linux as your work pc this will be your 1st step here) and type: 

`sudo apt update && sudo apt upgrade` 

and when it's finished, type 

`sudo apt install python3 git`

*git will be useful only if your company hasn't blocked access to github website*
- create directory for the game:

`mkdir your_folder_name`

and go inside it

`cd your_folder_name`

- now **if you can** access github from work PC type 

`git clone https://github.com/Fambly/Sloker.git`

if you can't, then somehow copy code to some pastebin and paste it inside the file

`nano whatever_you_wanna_call_it.py`

**Caution - pasting in `nano` is done by *ctrl + shift + v***

or you can just copy file with USB drive or any other creative way
- with `.py` file inside your directory just give it access to execute code:

`chmod +x whatever_you_called_it.py`
- to run program simply type `./whatever_you_called_it.py`

# How to use incognito mode?
Well, at any point of game you simply press `p` on keyboard to throw process with game to the background. It will then show terminal with some short message that would look like log analyzer and would tell you what to type so it would look like you're know what you're doing. 

To get back to the game simply type `fg` and your game would come back at exact moment you left it.

## My Little Theories
Transfering file to the company computer is easier than extracting it from it without showing up in some logs - I'd recomend to somehow copy the code offline if possible or just be aware if the IT team is looking at the log entries pointing to sites like github, pastebin or any file hosting sites. You're doing it at your own risk.

Running this directly from Windows or Linux is, in my opinion, a somewhat questionable idea, because the file would be stored **directly on the disk**. In a work environment, most people use Windows, and Windows has **WSL** - files from WSL aren’t stored directly on the disk; instead, the WSL2 data is physically stored in a *.vhdx* file. However, this doesn’t mean that some file scanner will simply treat it as a directory and scan all the files inside. It’s a virtual disk with an ext4 filesystem; to see what’s there from within Windows, you have to navigate to `\\wsl$` - this helps hide the file somewhat. WSL also runs as a terminal window in Windows, so if necessary, you can minimize that window or reposition it on the screen. The executable’s filename also doesn’t directly refer to anything, so it looks natural.

# Happy slacking off!
