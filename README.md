# ELAN-ASR

This is a Python script to use Google's speech-to-text API to transcribe annotations in a specified tier of an Elan project.




## Installation

1. Clone the repo & `cd` into `elan-asr/`.
2. Make a python env and activate

	`python -m venv env`
	
	`source env/bin/activate`
	
3. Install dependencies

	`pip install -r requirements.txt`
	
4. Use




## Usage	

Create an Elan project. Delimit speech on a given tier by creating annotations. Run the script. Specify the Elan file with `-e` or a list of Elan files with `-E` and the language to be speech-recognized with `-l`. Specify a tier by name with `-t` and / or an associated media file with `-m` (otherwise, the script will take the first media / tier it encounters in the Elan file).

	usage: elan-asr.py 

	[-h] [-e ELAN_FILE] [-E LIST_ELAN] [-t TIER] [-l LANGUAGE] [-L] [-m MEDIA_INDEX]

	[-M] [-k]

	Automatically run asr on a specified tier of an elan project. This program will read the tier make copies of media segments corresponding to annotation values, send that fragment to an asr API, then populate the return text value in that tier / annotation. Requires FFMPEG on system PATH environment.

	optional arguments:

	  -h, --help            show this help message and exit
  	-e ELAN_FILE, --elan-file ELAN_FILE
				Elan file (.eaf).
	  -E LIST_ELAN, --list-elan LIST_ELAN
				List of Elan files (.eaf).
	  -t TIER, --tier TIER  
	  			Exact name (case sensitive) of tier to operate on (if tiername contains spaces, wrap arg in quotes). If unset, script will operate on the first/top-level tier.
	  -l LANGUAGE, --language LANGUAGE
				Language to ASR (Use BCP-47 code).
	  -L, --language-options
	  			Print ASR language options.
	  -m MEDIA_INDEX, --media-index MEDIA_INDEX
				Select media file to work with. Use only in cases where there are multiple media files associated with the selected elan file. HINT: user `-M` to find media indexes.
	  -M, --media-indexes   Print associated media indexes.
	  -k, --keep-tmp        Don't delete temporary files generated by the script (txt files and sliced media files).




## Requirements

Aside from the python modules in the requirements file, ffmpeg must be installed on the users PATH environment.




## Licence

CC BY-SA




## Caveats

1. So far, this only works on alignable tier types. If there's any demand, it can be expanded to work with other tier types.