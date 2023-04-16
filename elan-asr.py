#!/usr/bin/env python3
"""
Automatically run asr on a specified tier of an elan project. This program will read the tier make copies of media segments corresponding to annotation values, send that fragment to an asr API, then populate the return text value in that tier / annotation. Requires FFMPEG on system PATH environment.
"""
from argparse import RawTextHelpFormatter
from tqdm import tqdm
import argparse, json, os, shutil, subprocess, sys
import speech_recognition as sr
import xml.etree.ElementTree as et




def find_media_indexes(elan):
	media_descriptors = elan.findall("HEADER/MEDIA_DESCRIPTOR")
	if len(media_descriptors) > 0:
		print("[INDEX]: [FILE]")
		print("---------------")
		for i, md in enumerate(media_descriptors):
			print(f"[{i}]: {md.get('RELATIVE_MEDIA_URL')[2:]}") 




def get_ts_dict(elan):
	tsd = {}
	order = elan.find("TIME_ORDER")
	for slot in order:
		tsd[slot.get("TIME_SLOT_ID")] = slot.get("TIME_VALUE")
	return tsd




def slice_media(media, annotation_id, start_time, end_time, tmp_dir):
	subprocess.call([
		"ffmpeg", 
		"-loglevel", "fatal", 
		"-hide_banner", 
		"-nostdin",
		"-i", media,
		"-ss", f"{int(start_time)/1000}",
		"-to", f"{int(end_time)/1000}",
		f"{tmp_dir}/{annotation_id}.wav"
	])
	return f"{tmp_dir}/{annotation_id}.wav"




def pretty(eaf_doc):
	eaf_doc.text = "\n    "
	header = eaf_doc.find("HEADER")
	header.text = "\n        "
	for i, sh in enumerate(header, start=1):
		if i != len(header):
			sh.tail = "\n        "
		else:
			sh.tail = "\n    "
	header.tail = "\n    "
	time_order = eaf_doc.find("TIME_ORDER")
	time_order.text = "\n        "
	nr_of_slots = len(time_order)
	for slot_idx, slot in enumerate(time_order, start=1):
		if slot_idx != nr_of_slots:
			slot.tail = "\n        "
		else:
			slot.tail = "\n    "
	time_order.tail = "\n    "
	tiers = eaf_doc.findall("TIER")
	for tier_idx, tier in enumerate(tiers, start=1):
		tier.tail = "\n    "
		tier.text = "\n        "
		for annotation_idx, annotation in enumerate(tier, start=1):
			nr_of_annotations = len(tier)
			if annotation_idx != nr_of_annotations:
				annotation.tail = "\n        "
			else:
				annotation.tail = "\n    "
			for alignable in tier:
				alignable.text = "\n            "
				for val in alignable:
					val.text = "\n                "
					val.tail = "\n        "
					for v in val:
						v.tail = "\n            "
	ling_types = eaf_doc.findall("LINGUISTIC_TYPE")
	for ling_type in ling_types:
		ling_type.tail = "\n    "
	constraints = eaf_doc.findall("CONSTRAINT")
	for ci, c in enumerate(constraints, start=1):
		if ci != len(constraints):
			c.tail = "\n    "
		else:
			c.tail = "\n"
	return eaf_doc				   




def srecognize(media, lang, annotation_id, tmp_dir):
	r = sr.Recognizer()
	bad_resp = None
	with sr.AudioFile(media) as source:
		audio = r.record(source)
		try:
			sr_response = r.recognize_google(audio, language=lang, show_all=True)
		except sr.UnknownValueError:
			bad_resp = "***U"
		except sr.RequestError as e:
			bad_resp = "Could not request results from Google Speech Recognition service".format(e)
	if len(sr_response) > 0:
		transcription = sr_response['alternative'][0]['transcript']
		with open(f"{tmp_dir}/{annotation_id}.json", 'w+') as outj:
			json.dump(sr_response, outj, indent=4, ensure_ascii=False)
	else:
		if bad_resp == None:
			bad_resp = '***'
		transcription = bad_resp
	return transcription




def main(args):
	eafs = []
	if args.elan_file:
		eafs.append(args.elan_file)
	elif args.list_elan:
		with open(args.list_elan, 'r') as inf:
			es = inf.readlines()
		[eafs.append(e.strip()) for e in es]

	for i, eaf in enumerate(eafs):
		print(f"Working on --| {eaf} |--	~~ {i+1} of {len(eafs)} ~~")
		e_parsed = et.parse(eaf)
		elan = e_parsed.getroot()
		if args.media_indexes:
			find_media_indexes(elan)
		else:
			try:
				md = elan.findall("HEADER/MEDIA_DESCRIPTOR")[args.media_index]
			except:
				print("There was a problem getting the media_descriptor. Probably you passed an index that doesn't exist (indexes start at --0--!); Try again.")
				sys.exit()
			media = md.get("MEDIA_URL")[7:]
			if not os.path.exists(media):
				print("\n\t The media file was not found or doesn't exist. Fix that & try again.\n")
				sys.exit()

			print("\t...getting time stamps...")
			ts_dict = get_ts_dict(elan)
			elan_path = os.path.dirname(os.path.abspath(eaf))
			tmp_dir = f"{elan_path}/tmp/{os.path.basename(eaf)[:-4]}"
			if not os.path.exists(f"{elan_path}/tmp"):
				os.mkdir(f"{elan_path}/tmp")
			if not os.path.exists(tmp_dir):
				print("\t...writing temporary dir...")
				os.mkdir(tmp_dir)	

			if args.tier:
				tier = elan.find(f"TIER[@TIER_ID='{args.tier}']")
			else:
				tier = elan.find("TIER")

			print("\t...iterating over tier...")
			for annotation in tqdm(tier, total=len(tier)):
				for alignable in annotation:
					annotation_id = alignable.get("ANNOTATION_ID")
					start_time = ts_dict[alignable.get("TIME_SLOT_REF1")]
					end_time = ts_dict[alignable.get("TIME_SLOT_REF2")]
					media_slice = slice_media(media, annotation_id, start_time, end_time, tmp_dir)
					tx = srecognize(media_slice, args.language, annotation_id, tmp_dir)
					tqdm.write(f"--> Annotation [{annotation_id}]: {tx}")
					for val in alignable:
						val.text = tx
			elan = pretty(elan)
			tree = et.ElementTree(elan)
			tree.write(eaf, encoding="utf-8", xml_declaration=True)

			if not args.keep_tmp:
				print("\t...removing temporary files")
				shutil.rmtree(tmp_dir)
				if len(os.listdir(f"{elan_path}/tmp/")) == 0:
					shutil.rmtree(f"{elan_path}/tmp")

		print(f"Finished ~~| {eaf} |~~ successfully!")
								
				
				

def print_language_opts():
	print("Language options for the Google Speech-to-Text API (as of 2023-04-16). If you use another API, the opts may be different.")
	print("""
Name 	BCP-47 	Model 	Automatic punctuation 	Diarization 	Model adaptation 	Word-level confidence 	Profanity filter 	Spoken punctuation 	Spoken emojis
Afrikaans (South Africa) 	af-ZA 	Command and search 			✔ 		✔ 		
Afrikaans (South Africa) 	af-ZA 	Default 			✔ 		✔ 		
Albanian (Albania) 	sq-AL 	Command and search 					✔ 		
Albanian (Albania) 	sq-AL 	Default 					✔ 		
Amharic (Ethiopia) 	am-ET 	Command and search 					✔ 		
Amharic (Ethiopia) 	am-ET 	Default 					✔ 		
Arabic (Algeria) 	ar-DZ 	Command and search 					✔ 		
Arabic (Algeria) 	ar-DZ 	Default 					✔ 		
Arabic (Algeria) 	ar-DZ 	Latest Long 				✔ 	✔ 		
Arabic (Algeria) 	ar-DZ 	Latest Short 				✔ 	✔ 		
Arabic (Bahrain) 	ar-BH 	Command and search 			✔ 		✔ 		
Arabic (Bahrain) 	ar-BH 	Default 			✔ 		✔ 		
Arabic (Bahrain) 	ar-BH 	Latest Long 				✔ 	✔ 		
Arabic (Bahrain) 	ar-BH 	Latest Short 				✔ 	✔ 		
Arabic (Egypt) 	ar-EG 	Command and search 			✔ 		✔ 		
Arabic (Egypt) 	ar-EG 	Default 			✔ 		✔ 		
Arabic (Egypt) 	ar-EG 	Latest Long 				✔ 	✔ 		
Arabic (Egypt) 	ar-EG 	Latest Short 				✔ 	✔ 		
Arabic (Iraq) 	ar-IQ 	Command and search 			✔ 		✔ 		
Arabic (Iraq) 	ar-IQ 	Default 			✔ 		✔ 		
Arabic (Iraq) 	ar-IQ 	Latest Long 				✔ 	✔ 		
Arabic (Iraq) 	ar-IQ 	Latest Short 				✔ 	✔ 		
Arabic (Israel) 	ar-IL 	Command and search 			✔ 		✔ 		
Arabic (Israel) 	ar-IL 	Default 			✔ 		✔ 		
Arabic (Israel) 	ar-IL 	Latest Long 				✔ 	✔ 		
Arabic (Israel) 	ar-IL 	Latest Short 				✔ 	✔ 		
Arabic (Jordan) 	ar-JO 	Command and search 			✔ 		✔ 		
Arabic (Jordan) 	ar-JO 	Default 			✔ 		✔ 		
Arabic (Jordan) 	ar-JO 	Latest Long 				✔ 	✔ 		
Arabic (Jordan) 	ar-JO 	Latest Short 				✔ 	✔ 		
Arabic (Kuwait) 	ar-KW 	Command and search 			✔ 		✔ 		
Arabic (Kuwait) 	ar-KW 	Default 			✔ 		✔ 		
Arabic (Kuwait) 	ar-KW 	Latest Long 				✔ 	✔ 		
Arabic (Kuwait) 	ar-KW 	Latest Short 				✔ 	✔ 		
Arabic (Lebanon) 	ar-LB 	Command and search 			✔ 		✔ 		
Arabic (Lebanon) 	ar-LB 	Default 			✔ 		✔ 		
Arabic (Lebanon) 	ar-LB 	Latest Long 				✔ 	✔ 		
Arabic (Lebanon) 	ar-LB 	Latest Short 				✔ 	✔ 		
Arabic (Mauritania) 	ar-MR 	Latest Long 				✔ 	✔ 		
Arabic (Mauritania) 	ar-MR 	Latest Short 				✔ 	✔ 		
Arabic (Morocco) 	ar-MA 	Command and search 					✔ 		
Arabic (Morocco) 	ar-MA 	Default 					✔ 		
Arabic (Morocco) 	ar-MA 	Latest Long 				✔ 	✔ 		
Arabic (Morocco) 	ar-MA 	Latest Short 				✔ 	✔ 		
Arabic (Oman) 	ar-OM 	Command and search 			✔ 		✔ 		
Arabic (Oman) 	ar-OM 	Default 			✔ 		✔ 		
Arabic (Oman) 	ar-OM 	Latest Long 				✔ 	✔ 		
Arabic (Oman) 	ar-OM 	Latest Short 				✔ 	✔ 		
Arabic (Qatar) 	ar-QA 	Command and search 			✔ 		✔ 		
Arabic (Qatar) 	ar-QA 	Default 			✔ 		✔ 		
Arabic (Qatar) 	ar-QA 	Latest Long 				✔ 	✔ 		
Arabic (Qatar) 	ar-QA 	Latest Short 				✔ 	✔ 		
Arabic (Saudi Arabia) 	ar-SA 	Command and search 			✔ 		✔ 		
Arabic (Saudi Arabia) 	ar-SA 	Default 			✔ 		✔ 		
Arabic (Saudi Arabia) 	ar-SA 	Latest Long 				✔ 	✔ 		
Arabic (Saudi Arabia) 	ar-SA 	Latest Short 				✔ 	✔ 		
Arabic (State of Palestine) 	ar-PS 	Command and search 			✔ 		✔ 		
Arabic (State of Palestine) 	ar-PS 	Default 			✔ 		✔ 		
Arabic (State of Palestine) 	ar-PS 	Latest Long 				✔ 	✔ 		
Arabic (State of Palestine) 	ar-PS 	Latest Short 				✔ 	✔ 		
Arabic (Tunisia) 	ar-TN 	Command and search 					✔ 		
Arabic (Tunisia) 	ar-TN 	Default 					✔ 		
Arabic (Tunisia) 	ar-TN 	Latest Long 				✔ 	✔ 		
Arabic (Tunisia) 	ar-TN 	Latest Short 				✔ 	✔ 		
Arabic (United Arab Emirates) 	ar-AE 	Command and search 			✔ 		✔ 		
Arabic (United Arab Emirates) 	ar-AE 	Default 			✔ 		✔ 		
Arabic (United Arab Emirates) 	ar-AE 	Latest Long 				✔ 	✔ 		
Arabic (United Arab Emirates) 	ar-AE 	Latest Short 				✔ 	✔ 		
Arabic (Yemen) 	ar-YE 	Command and search 					✔ 		
Arabic (Yemen) 	ar-YE 	Default 					✔ 		
Arabic (Yemen) 	ar-YE 	Latest Long 				✔ 	✔ 		
Arabic (Yemen) 	ar-YE 	Latest Short 				✔ 	✔ 		
Armenian (Armenia) 	hy-AM 	Command and search 					✔ 		
Armenian (Armenia) 	hy-AM 	Default 					✔ 		
Azerbaijani (Azerbaijan) 	az-AZ 	Command and search 					✔ 		
Azerbaijani (Azerbaijan) 	az-AZ 	Default 					✔ 		
Basque (Spain) 	eu-ES 	Command and search 					✔ 		
Basque (Spain) 	eu-ES 	Default 					✔ 		
Bengali (Bangladesh) 	bn-BD 	Command and search 			✔ 		✔ 		
Bengali (Bangladesh) 	bn-BD 	Default 			✔ 		✔ 		
Bengali (Bangladesh) 	bn-BD 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Bengali (Bangladesh) 	bn-BD 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Bengali (India) 	bn-IN 	Command and search 					✔ 		
Bengali (India) 	bn-IN 	Default 					✔ 		
Bosnian (Bosnia and Herzegovina) 	bs-BA 	Command and search 					✔ 		
Bosnian (Bosnia and Herzegovina) 	bs-BA 	Default 					✔ 		
Bulgarian (Bulgaria) 	bg-BG 	Command and search 					✔ 		
Bulgarian (Bulgaria) 	bg-BG 	Default 					✔ 		
Bulgarian (Bulgaria) 	bg-BG 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Bulgarian (Bulgaria) 	bg-BG 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Burmese (Myanmar) 	my-MM 	Command and search 					✔ 		
Burmese (Myanmar) 	my-MM 	Default 					✔ 		
Catalan (Spain) 	ca-ES 	Command and search 					✔ 		
Catalan (Spain) 	ca-ES 	Default 					✔ 		
Chinese, Cantonese (Traditional Hong Kong) 	yue-Hant-HK 	Command and search 			✔ 		✔ 		
Chinese, Cantonese (Traditional Hong Kong) 	yue-Hant-HK 	Default 			✔ 		✔ 		
Chinese, Mandarin (Simplified, China) 	zh (cmn-Hans-CN) 	Command and search 	✔ 	✔ 	✔ 		✔ 		
Chinese, Mandarin (Simplified, China) 	zh (cmn-Hans-CN) 	Default 	✔ 	✔ 	✔ 		✔ 		
Chinese, Mandarin (Traditional, Taiwan) 	zh-TW (cmn-Hant-TW) 	Command and search 	✔ 		✔ 		✔ 		
Chinese, Mandarin (Traditional, Taiwan) 	zh-TW (cmn-Hant-TW) 	Default 	✔ 		✔ 		✔ 		
Croatian (Croatia) 	hr-HR 	Command and search 					✔ 		
Croatian (Croatia) 	hr-HR 	Default 					✔ 		
Czech (Czech Republic) 	cs-CZ 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Czech (Czech Republic) 	cs-CZ 	Default 	✔ 		✔ 		✔ 	✔ 	
Czech (Czech Republic) 	cs-CZ 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Czech (Czech Republic) 	cs-CZ 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Danish (Denmark) 	da-DK 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Danish (Denmark) 	da-DK 	Default 	✔ 		✔ 		✔ 	✔ 	
Danish (Denmark) 	da-DK 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Danish (Denmark) 	da-DK 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Dutch (Belgium) 	nl-BE 	Command and search 					✔ 	✔ 	
Dutch (Belgium) 	nl-BE 	Default 					✔ 	✔ 	
Dutch (Netherlands) 	nl-NL 	Command and search 			✔ 		✔ 	✔ 	
Dutch (Netherlands) 	nl-NL 	Default 			✔ 		✔ 	✔ 	
Dutch (Netherlands) 	nl-NL 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Dutch (Netherlands) 	nl-NL 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
English (Australia) 	en-AU 	Command and search 	✔ 		✔ 		✔ 	✔ 	✔
English (Australia) 	en-AU 	Default 	✔ 		✔ 		✔ 	✔ 	✔
English (Australia) 	en-AU 	Enhanced phone call 	✔ 			✔ 	✔ 		
English (Australia) 	en-AU 	Latest Long 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
English (Australia) 	en-AU 	Latest Short 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
English (Canada) 	en-CA 	Command and search 					✔ 	✔ 	✔
English (Canada) 	en-CA 	Default 					✔ 		
English (Ghana) 	en-GH 	Command and search 			✔ 		✔ 	✔ 	
English (Ghana) 	en-GH 	Default 			✔ 		✔ 	✔ 	
English (Hong Kong) 	en-HK 	Command and search 					✔ 	✔ 	✔
English (Hong Kong) 	en-HK 	Default 					✔ 	✔ 	✔
English (India) 	en-IN 	Command and search 	✔ 	✔ 	✔ 		✔ 	✔ 	✔
English (India) 	en-IN 	Default 	✔ 	✔ 	✔ 		✔ 	✔ 	✔
English (India) 	en-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	✔
English (India) 	en-IN 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	✔
English (Ireland) 	en-IE 	Command and search 					✔ 	✔ 	✔
English (Ireland) 	en-IE 	Default 					✔ 	✔ 	✔
English (Kenya) 	en-KE 	Command and search 			✔ 		✔ 	✔ 	
English (Kenya) 	en-KE 	Default 			✔ 		✔ 	✔ 	
English (New Zealand) 	en-NZ 	Command and search 					✔ 	✔ 	✔
English (New Zealand) 	en-NZ 	Default 					✔ 	✔ 	✔
English (Nigeria) 	en-NG 	Command and search 			✔ 		✔ 	✔ 	
English (Nigeria) 	en-NG 	Default 			✔ 		✔ 	✔ 	
English (Pakistan) 	en-PK 	Command and search 					✔ 	✔ 	✔
English (Pakistan) 	en-PK 	Default 					✔ 	✔ 	✔
English (Philippines) 	en-PH 	Command and search 			✔ 		✔ 		✔
English (Philippines) 	en-PH 	Default 			✔ 		✔ 		
English (Singapore) 	en-SG 	Command and search 	✔ 	✔ 	✔ 	✔ 	✔ 	✔ 	✔
English (Singapore) 	en-SG 	Default 	✔ 	✔ 	✔ 	✔ 	✔ 		
English (South Africa) 	en-ZA 	Command and search 			✔ 		✔ 	✔ 	
English (South Africa) 	en-ZA 	Default 			✔ 		✔ 	✔ 	
English (Tanzania) 	en-TZ 	Command and search 			✔ 		✔ 	✔ 	
English (Tanzania) 	en-TZ 	Default 			✔ 		✔ 	✔ 	
English (United Kingdom) 	en-GB 	Command and search 	✔ 	✔ 	✔ 		✔ 	✔ 	✔
English (United Kingdom) 	en-GB 	Default 	✔ 	✔ 	✔ 		✔ 	✔ 	✔
English (United Kingdom) 	en-GB 	Enhanced phone call 	✔ 	✔ 			✔ 	✔ 	✔
English (United Kingdom) 	en-GB 	Latest Long 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
English (United Kingdom) 	en-GB 	Latest Short 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
English (United States) 	en-US 	Command and search 	✔ 	✔ 	✔ 	✔ 	✔ 	✔ 	✔
English (United States) 	en-US 	Default 	✔ 	✔ 	✔ 	✔ 	✔ 		
English (United States) 	en-US 	Enhanced phone call 	✔ 	✔ 	✔ 	✔ 	✔ 		
English (United States) 	en-US 	Enhanced video 	✔ 	✔ 	✔ 	✔ 	✔ 		
English (United States) 	en-US 	Latest Long 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
English (United States) 	en-US 	Latest Short 	✔ 	✔ 	✔ 	✔ 	✔ 	✔ 	✔
English (United States) 	en-US 	Medical Conversation 		✔ 					
English (United States) 	en-US 	Medical Dictation 							
Estonian (Estonia) 	et-EE 	Command and search 					✔ 		
Estonian (Estonia) 	et-EE 	Default 					✔ 		
Filipino (Philippines) 	fil-PH 	Command and search 			✔ 		✔ 		
Filipino (Philippines) 	fil-PH 	Default 			✔ 		✔ 		
Finnish (Finland) 	fi-FI 	Command and search 	✔ 		✔ 		✔ 		
Finnish (Finland) 	fi-FI 	Default 	✔ 		✔ 		✔ 		
Finnish (Finland) 	fi-FI 	Latest Long 	✔ 			✔ 	✔ 		
Finnish (Finland) 	fi-FI 	Latest Short 	✔ 			✔ 	✔ 		
French (Belgium) 	fr-BE 	Command and search 					✔ 	✔ 	✔
French (Belgium) 	fr-BE 	Default 					✔ 	✔ 	✔
French (Canada) 	fr-CA 	Command and search 			✔ 		✔ 	✔ 	
French (Canada) 	fr-CA 	Default 			✔ 		✔ 	✔ 	
French (Canada) 	fr-CA 	Enhanced phone call 				✔ 	✔ 		
French (Canada) 	fr-CA 	Latest Long 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
French (Canada) 	fr-CA 	Latest Short 	✔ 	✔ 	✔ 	✔ 	✔ 	✔ 	✔
French (France) 	fr-FR 	Command and search 	✔ 	✔ 	✔ 		✔ 	✔ 	✔
French (France) 	fr-FR 	Default 	✔ 	✔ 	✔ 		✔ 	✔ 	✔
French (France) 	fr-FR 	Enhanced phone call 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
French (France) 	fr-FR 	Latest Long 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
French (France) 	fr-FR 	Latest Short 	✔ 	✔ 	✔ 	✔ 	✔ 	✔ 	✔
French (Switzerland) 	fr-CH 	Command and search 					✔ 	✔ 	✔
French (Switzerland) 	fr-CH 	Default 					✔ 	✔ 	✔
Galician (Spain) 	gl-ES 	Command and search 					✔ 		
Galician (Spain) 	gl-ES 	Default 					✔ 		
Georgian (Georgia) 	ka-GE 	Command and search 					✔ 		
Georgian (Georgia) 	ka-GE 	Default 					✔ 		
German (Austria) 	de-AT 	Command and search 					✔ 	✔ 	
German (Austria) 	de-AT 	Default 					✔ 	✔ 	
German (Germany) 	de-DE 	Command and search 	✔ 	✔ 	✔ 		✔ 	✔ 	
German (Germany) 	de-DE 	Default 	✔ 	✔ 	✔ 		✔ 	✔ 	
German (Germany) 	de-DE 	Enhanced phone call 	✔ 	✔ 			✔ 	✔ 	
German (Germany) 	de-DE 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
German (Germany) 	de-DE 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
German (Switzerland) 	de-CH 	Command and search 					✔ 	✔ 	
German (Switzerland) 	de-CH 	Default 					✔ 	✔ 	
Greek (Greece) 	el-GR 	Command and search 					✔ 		
Greek (Greece) 	el-GR 	Default 					✔ 		
Gujarati (India) 	gu-IN 	Command and search 			✔ 		✔ 		
Gujarati (India) 	gu-IN 	Default 			✔ 		✔ 		
Hebrew (Israel) 	iw-IL 	Command and search 			✔ 		✔ 	✔ 	
Hebrew (Israel) 	iw-IL 	Default 			✔ 		✔ 	✔ 	
Hindi (India) 	hi-IN 	Command and search 			✔ 		✔ 	✔ 	
Hindi (India) 	hi-IN 	Default 			✔ 		✔ 	✔ 	
Hindi (India) 	hi-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Hindi (India) 	hi-IN 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	
Hungarian (Hungary) 	hu-HU 	Command and search 					✔ 		
Hungarian (Hungary) 	hu-HU 	Default 					✔ 		
Hungarian (Hungary) 	hu-HU 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Hungarian (Hungary) 	hu-HU 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Icelandic (Iceland) 	is-IS 	Command and search 					✔ 		
Icelandic (Iceland) 	is-IS 	Default 					✔ 		
Indonesian (Indonesia) 	id-ID 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Indonesian (Indonesia) 	id-ID 	Default 	✔ 		✔ 		✔ 	✔ 	
Indonesian (Indonesia) 	id-ID 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Indonesian (Indonesia) 	id-ID 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	
Italian (Italy) 	it-IT 	Command and search 	✔ 	✔ 	✔ 		✔ 	✔ 	
Italian (Italy) 	it-IT 	Default 	✔ 	✔ 	✔ 		✔ 	✔ 	
Italian (Italy) 	it-IT 	Enhanced phone call 	✔ 	✔ 			✔ 	✔ 	
Italian (Italy) 	it-IT 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Italian (Italy) 	it-IT 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	
Italian (Switzerland) 	it-CH 	Command and search 					✔ 	✔ 	
Italian (Switzerland) 	it-CH 	Default 					✔ 	✔ 	
Japanese (Japan) 	ja-JP 	Command and search 	✔ 	✔ 	✔ 		✔ 	✔ 	
Japanese (Japan) 	ja-JP 	Default 	✔ 	✔ 	✔ 		✔ 	✔ 	
Japanese (Japan) 	ja-JP 	Enhanced phone call 	✔ 	✔ 		✔ 	✔ 	✔ 	
Japanese (Japan) 	ja-JP 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Japanese (Japan) 	ja-JP 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	
Javanese (Indonesia) 	jv-ID 	Command and search 					✔ 		
Javanese (Indonesia) 	jv-ID 	Default 					✔ 		
Kannada (India) 	kn-IN 	Command and search 			✔ 		✔ 		
Kannada (India) 	kn-IN 	Default 			✔ 		✔ 		
Kannada (India) 	kn-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Kannada (India) 	kn-IN 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Kazakh (Kazakhstan) 	kk-KZ 	Command and search 					✔ 		
Kazakh (Kazakhstan) 	kk-KZ 	Default 					✔ 		
Khmer (Cambodia) 	km-KH 	Command and search 					✔ 		
Khmer (Cambodia) 	km-KH 	Default 					✔ 		
Khmer (Cambodia) 	km-KH 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Khmer (Cambodia) 	km-KH 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Korean (South Korea) 	ko-KR 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Korean (South Korea) 	ko-KR 	Default 	✔ 		✔ 		✔ 	✔ 	
Korean (South Korea) 	ko-KR 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Korean (South Korea) 	ko-KR 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	
Lao (Laos) 	lo-LA 	Command and search 					✔ 		
Lao (Laos) 	lo-LA 	Default 					✔ 		
Latvian (Latvia) 	lv-LV 	Command and search 					✔ 		
Latvian (Latvia) 	lv-LV 	Default 					✔ 		
Lithuanian (Lithuania) 	lt-LT 	Command and search 					✔ 		
Lithuanian (Lithuania) 	lt-LT 	Default 					✔ 		
Macedonian (North Macedonia) 	mk-MK 	Command and search 					✔ 		
Macedonian (North Macedonia) 	mk-MK 	Default 					✔ 		
Macedonian (North Macedonia) 	mk-MK 	Latest Long 				✔ 	✔ 		
Macedonian (North Macedonia) 	mk-MK 	Latest Short 				✔ 	✔ 		
Malay (Malaysia) 	ms-MY 	Command and search 			✔ 		✔ 		
Malay (Malaysia) 	ms-MY 	Default 			✔ 		✔ 		
Malayalam (India) 	ml-IN 	Command and search 			✔ 		✔ 	✔ 	
Malayalam (India) 	ml-IN 	Default 			✔ 		✔ 	✔ 	
Malayalam (India) 	ml-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Malayalam (India) 	ml-IN 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Marathi (India) 	mr-IN 	Command and search 			✔ 		✔ 		
Marathi (India) 	mr-IN 	Default 			✔ 		✔ 		
Marathi (India) 	mr-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Marathi (India) 	mr-IN 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Mongolian (Mongolia) 	mn-MN 	Command and search 					✔ 		
Mongolian (Mongolia) 	mn-MN 	Default 					✔ 		
Nepali (Nepal) 	ne-NP 	Command and search 					✔ 		
Nepali (Nepal) 	ne-NP 	Default 					✔ 		
Norwegian Bokmål (Norway) 	no-NO 	Command and search 			✔ 		✔ 	✔ 	
Norwegian Bokmål (Norway) 	no-NO 	Default 			✔ 		✔ 	✔ 	
Norwegian Bokmål (Norway) 	no-NO 	Latest Long 				✔ 	✔ 	✔ 	
Norwegian Bokmål (Norway) 	no-NO 	Latest Short 				✔ 	✔ 	✔ 	
Persian (Iran) 	fa-IR 	Command and search 			✔ 		✔ 		
Persian (Iran) 	fa-IR 	Default 			✔ 		✔ 		
Polish (Poland) 	pl-PL 	Command and search 			✔ 		✔ 	✔ 	
Polish (Poland) 	pl-PL 	Default 			✔ 		✔ 	✔ 	
Polish (Poland) 	pl-PL 	Latest Long 				✔ 	✔ 	✔ 	
Polish (Poland) 	pl-PL 	Latest Short 				✔ 	✔ 	✔ 	
Portuguese (Brazil) 	pt-BR 	Command and search 		✔ 	✔ 		✔ 	✔ 	
Portuguese (Brazil) 	pt-BR 	Default 		✔ 	✔ 		✔ 	✔ 	
Portuguese (Brazil) 	pt-BR 	Enhanced phone call 	✔ 	✔ 		✔ 	✔ 	✔ 	
Portuguese (Brazil) 	pt-BR 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Portuguese (Brazil) 	pt-BR 	Latest Short 	✔ 		✔ 	✔ 	✔ 	✔ 	
Portuguese (Portugal) 	pt-PT 	Command and search 			✔ 		✔ 	✔ 	
Portuguese (Portugal) 	pt-PT 	Default 			✔ 		✔ 	✔ 	
Portuguese (Portugal) 	pt-PT 	Latest Long 				✔ 	✔ 	✔ 	
Portuguese (Portugal) 	pt-PT 	Latest Short 			✔ 	✔ 	✔ 	✔ 	
Punjabi (Gurmukhi India) 	pa-Guru-IN 	Command and search 					✔ 		
Punjabi (Gurmukhi India) 	pa-Guru-IN 	Default 					✔ 		
Romanian (Romania) 	ro-RO 	Command and search 					✔ 		
Romanian (Romania) 	ro-RO 	Default 					✔ 		
Romanian (Romania) 	ro-RO 	Latest Long 				✔ 	✔ 		
Romanian (Romania) 	ro-RO 	Latest Short 				✔ 	✔ 		
Russian (Russia) 	ru-RU 	Command and search 		✔ 	✔ 		✔ 	✔ 	
Russian (Russia) 	ru-RU 	Default 		✔ 	✔ 		✔ 	✔ 	
Russian (Russia) 	ru-RU 	Enhanced phone call 		✔ 			✔ 	✔ 	
Russian (Russia) 	ru-RU 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Russian (Russia) 	ru-RU 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Kinyarwanda (Rwanda) 	rw-RW 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Kinyarwanda (Rwanda) 	rw-RW 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Serbian (Serbia) 	sr-RS 	Command and search 			✔ 		✔ 		
Serbian (Serbia) 	sr-RS 	Default 			✔ 		✔ 		
Sinhala (Sri Lanka) 	si-LK 	Command and search 					✔ 		
Sinhala (Sri Lanka) 	si-LK 	Default 					✔ 		
Slovak (Slovakia) 	sk-SK 	Command and search 					✔ 		
Slovak (Slovakia) 	sk-SK 	Default 					✔ 		
Slovenian (Slovenia) 	sl-SI 	Command and search 					✔ 		
Slovenian (Slovenia) 	sl-SI 	Default 					✔ 		
Swati (South Africa) 	ss-latn-za 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Swati (South Africa) 	ss-latn-za 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Southern Sotho (South Africa) 	st-ZA 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Southern Sotho (South Africa) 	st-ZA 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Spanish (Argentina) 	es-AR 	Command and search 					✔ 	✔ 	
Spanish (Argentina) 	es-AR 	Default 					✔ 	✔ 	
Spanish (Bolivia) 	es-BO 	Command and search 					✔ 	✔ 	
Spanish (Bolivia) 	es-BO 	Default 					✔ 	✔ 	
Spanish (Chile) 	es-CL 	Command and search 					✔ 	✔ 	
Spanish (Chile) 	es-CL 	Default 					✔ 	✔ 	
Spanish (Colombia) 	es-CO 	Command and search 					✔ 	✔ 	
Spanish (Colombia) 	es-CO 	Default 					✔ 	✔ 	
Spanish (Costa Rica) 	es-CR 	Command and search 					✔ 	✔ 	
Spanish (Costa Rica) 	es-CR 	Default 					✔ 	✔ 	
Spanish (Dominican Republic) 	es-DO 	Command and search 					✔ 	✔ 	
Spanish (Dominican Republic) 	es-DO 	Default 					✔ 	✔ 	
Spanish (Ecuador) 	es-EC 	Command and search 					✔ 	✔ 	
Spanish (Ecuador) 	es-EC 	Default 					✔ 	✔ 	
Spanish (El Salvador) 	es-SV 	Command and search 					✔ 	✔ 	
Spanish (El Salvador) 	es-SV 	Default 					✔ 	✔ 	
Spanish (Guatemala) 	es-GT 	Command and search 					✔ 	✔ 	
Spanish (Guatemala) 	es-GT 	Default 					✔ 	✔ 	
Spanish (Honduras) 	es-HN 	Command and search 					✔ 	✔ 	
Spanish (Honduras) 	es-HN 	Default 					✔ 	✔ 	
Spanish (Mexico) 	es-MX 	Command and search 					✔ 	✔ 	
Spanish (Mexico) 	es-MX 	Default 					✔ 	✔ 	
Spanish (Nicaragua) 	es-NI 	Command and search 					✔ 	✔ 	
Spanish (Nicaragua) 	es-NI 	Default 					✔ 	✔ 	
Spanish (Panama) 	es-PA 	Command and search 					✔ 	✔ 	
Spanish (Panama) 	es-PA 	Default 					✔ 	✔ 	
Spanish (Paraguay) 	es-PY 	Command and search 					✔ 	✔ 	
Spanish (Paraguay) 	es-PY 	Default 					✔ 	✔ 	
Spanish (Peru) 	es-PE 	Command and search 					✔ 	✔ 	
Spanish (Peru) 	es-PE 	Default 					✔ 	✔ 	
Spanish (Puerto Rico) 	es-PR 	Command and search 					✔ 	✔ 	
Spanish (Puerto Rico) 	es-PR 	Default 					✔ 	✔ 	
Spanish (Spain) 	es-ES 	Command and search 		✔ 	✔ 		✔ 	✔ 	
Spanish (Spain) 	es-ES 	Default 		✔ 	✔ 		✔ 	✔ 	
Spanish (Spain) 	es-ES 	Enhanced phone call 		✔ 		✔ 	✔ 	✔ 	
Spanish (Spain) 	es-ES 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Spanish (Spain) 	es-ES 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Spanish (United States) 	es-US 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Spanish (United States) 	es-US 	Default 	✔ 		✔ 		✔ 	✔ 	
Spanish (United States) 	es-US 	Enhanced phone call 	✔ 				✔ 	✔ 	
Spanish (United States) 	es-US 	Latest Long 	✔ 	✔ 		✔ 	✔ 	✔ 	✔
Spanish (United States) 	es-US 	Latest Short 	✔ 	✔ 	✔ 	✔ 	✔ 	✔ 	✔
Spanish (Uruguay) 	es-UY 	Command and search 					✔ 	✔ 	
Spanish (Uruguay) 	es-UY 	Default 					✔ 	✔ 	
Spanish (Venezuela) 	es-VE 	Command and search 					✔ 	✔ 	
Spanish (Venezuela) 	es-VE 	Default 					✔ 	✔ 	
Sundanese (Indonesia) 	su-ID 	Command and search 					✔ 		
Sundanese (Indonesia) 	su-ID 	Default 					✔ 		
Swahili (Kenya) 	sw-KE 	Command and search 					✔ 		
Swahili (Kenya) 	sw-KE 	Default 					✔ 		
Swahili (Tanzania) 	sw-TZ 	Command and search 					✔ 		
Swahili (Tanzania) 	sw-TZ 	Default 					✔ 		
Swedish (Sweden) 	sv-SE 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Swedish (Sweden) 	sv-SE 	Default 	✔ 		✔ 		✔ 	✔ 	
Swedish (Sweden) 	sv-SE 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Swedish (Sweden) 	sv-SE 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Tamil (India) 	ta-IN 	Command and search 			✔ 		✔ 		
Tamil (India) 	ta-IN 	Default 			✔ 		✔ 		
Tamil (India) 	ta-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Tamil (India) 	ta-IN 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Tamil (Malaysia) 	ta-MY 	Command and search 					✔ 		
Tamil (Malaysia) 	ta-MY 	Default 					✔ 		
Tamil (Singapore) 	ta-SG 	Command and search 					✔ 		
Tamil (Singapore) 	ta-SG 	Default 					✔ 		
Tamil (Sri Lanka) 	ta-LK 	Command and search 					✔ 		
Tamil (Sri Lanka) 	ta-LK 	Default 					✔ 		
Telugu (India) 	te-IN 	Command and search 			✔ 		✔ 		
Telugu (India) 	te-IN 	Default 			✔ 		✔ 		
Telugu (India) 	te-IN 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Telugu (India) 	te-IN 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Thai (Thailand) 	th-TH 	Command and search 			✔ 		✔ 		
Thai (Thailand) 	th-TH 	Default 			✔ 		✔ 		
Thai (Thailand) 	th-TH 	Latest Long 				✔ 	✔ 		
Thai (Thailand) 	th-TH 	Latest Short 				✔ 	✔ 		
Setswana (South Africa) 	tn-latn-za 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Setswana (South Africa) 	tn-latn-za 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Turkish (Turkey) 	tr-TR 	Command and search 	✔ 		✔ 		✔ 	✔ 	
Turkish (Turkey) 	tr-TR 	Default 	✔ 		✔ 		✔ 	✔ 	
Turkish (Turkey) 	tr-TR 	Latest Long 				✔ 	✔ 	✔ 	
Turkish (Turkey) 	tr-TR 	Latest Short 				✔ 	✔ 	✔ 	
Tsonga (South Africa) 	ts-ZA 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Tsonga (South Africa) 	ts-ZA 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Ukrainian (Ukraine) 	uk-UA 	Command and search 			✔ 		✔ 		
Ukrainian (Ukraine) 	uk-UA 	Default 			✔ 		✔ 		
Ukrainian (Ukraine) 	uk-UA 	Latest Long 				✔ 	✔ 		
Ukrainian (Ukraine) 	uk-UA 	Latest Short 			✔ 	✔ 	✔ 		
Urdu (India) 	ur-IN 	Command and search 					✔ 		
Urdu (India) 	ur-IN 	Default 					✔ 		
Urdu (Pakistan) 	ur-PK 	Command and search 			✔ 		✔ 		
Urdu (Pakistan) 	ur-PK 	Default 			✔ 		✔ 		
Uzbek (Uzbekistan) 	uz-UZ 	Command and search 					✔ 		
Uzbek (Uzbekistan) 	uz-UZ 	Default 					✔ 		
Venda (South Africa) 	ve-ZA 	Latest Long 	✔ 			✔ 	✔ 	✔ 	
Venda (South Africa) 	ve-ZA 	Latest Short 	✔ 			✔ 	✔ 	✔ 	
Vietnamese (Vietnam) 	vi-VN 	Command and search 			✔ 		✔ 		
Vietnamese (Vietnam) 	vi-VN 	Default 			✔ 		✔ 		
Vietnamese (Vietnam) 	vi-VN 	Latest Long 	✔ 			✔ 	✔ 		
Vietnamese (Vietnam) 	vi-VN 	Latest Short 	✔ 			✔ 	✔ 		
isiXhosa (South Africa) 	xh-ZA 	Latest Long 	✔ 			✔ 	✔ 		
isiXhosa (South Africa) 	xh-ZA 	Latest Short 	✔ 			✔ 	✔ 		
Zulu (South Africa) 	zu-ZA 	Command and search 			✔ 		✔ 		
Zulu (South Africa) 	zu-ZA 	Default 			✔ 		✔ 		
""")




if __name__ == '__main__':
	parser = argparse.ArgumentParser(description=__doc__,  formatter_class=RawTextHelpFormatter)
	parser.add_argument("-e", "--elan-file", type=str, default=None, help="Elan file (.eaf).")
	parser.add_argument("-E", "--list-elan", type=str, default=None, help="List of Elan files (.eaf).")
	parser.add_argument("-t", "--tier", type=str, default=None, 
		help="Exact name (case sensitive) of tier to operate on (if tiername contains spaces, wrap arg in quotes). If unset, script will operate on the first/top-level tier.")
	parser.add_argument("-l", "--language", type=str, help="Language to ASR (Use BCP-47 code).")
	parser.add_argument("-L", "--language-options", action="store_true", help="Print ASR language options.")
	parser.add_argument("-m", "--media-index", type=int, default=0, 
		help="Select media file to work with. Use only in cases where there are multiple media files associated with the selected elan file. HINT: user `-M` to find media indexes.")
	parser.add_argument("-M", "--media-indexes", action="store_true", help="Print associated media indexes.")
	parser.add_argument("-k", "--keep-tmp", action="store_true", 
		help="Don't delete temporary files generated by the script (txt files and sliced media files).")
	args = parser.parse_args()
	if args.language_options:
		print_language_opts()
	elif args.elan_file or args.list_elan:
		main(args)
	else:
		parser.print_help()

