import sys  # systemoperationen... meist nur als sys.exit(0) genutzt
import argparse  # Kommandozeilenargumente einlesen und auswerten.
import numpy # NUmerical Python... kernstück dieses Programms
# from qrcodegenmod import _qrcodegenmod_numba_draw_codewords  # <-- funktioniert.
import qrcodegenmod
import imageio  # Erstellung und Verarbeitung von Bildern und Videos
import cv2  # OpenCV... zum Debuggen und Bilder anzeigen bzw ggf. einlesen
import subprocess  # For Show File in Explorer
import multiprocessing # Parallel Abarbeitung der QR Code Erstellung
import time # Ein paar Zwischeninformationen sind immer interessant.
import os # Alles was hier mit Dateioperationen zu tun hat...
import glob  # um eine Datei zu finden, die schon für den Empfänger verschlüsselt wurde.
import threading  # Verwendet für das Wegschreiben der Videodatei, weil es so lange dauert und blockiert!
import gnupg  # Für QRCrypt Klasse und darin enthaltenen Methoden.
import upload_video  # upload_video.py im gleichen Verzeichnis
import analyze_video  # Video zu PGP Datei... separate python datei im gleichen ordner
import youtube_dl  # Download von Youtube Videos... separate python datei im gleichen ordner
import pyzbar.pyzbar as pyzbar  # Class QRCodeTools
from pyzbar.pyzbar import ZBarSymbol  # Class QRCodeTools

class YT:
    """ This class should simplify the usage of the youtube api for uploading a local video
    Further, it makes it easy to download a video via the youtube link id
    It saves the last uploaded and downloaded file information for later use
    """

    def __init__(self):
        pass

    def upload_video(self, video_filename, mytitle="Test Title", mydescription="Test Description"):
        """ This function uploads the video to youtube.
        The Video is NOT public by default.
        It is unlisted, so it is not private.
        Unlisted = Video can be seen, if the URL is known by a closed group of people
        Private = Video can only be seen by the owner.
        Todo: Change mytitle and mydescription. Make it mandatory.

        :param video_filename: The full path to the file, which should be uploaded.
        :param mytitle: the title of the video.
        :param mydescription: the description of the title

        """
        upload_video.argparser.add_argument("--file", default=video_filename, help="Video file to upload")
        upload_video.argparser.add_argument("--title", help="Video title", default=mytitle)
        upload_video.argparser.add_argument("--description", help="Video description",
                                            default=mydescription)
        upload_video.argparser.add_argument("--category",
                                            default="28",  # Science and Technology :-)
                                            help="Numeric video category. " +
                                                 "See https://developers.google.com/youtube/v3/docs/videoCategories/list")
        upload_video.argparser.add_argument("--keywords",
                                            help="Video keywords, comma separated",
                                            default="FOM-Thesis")  # Ein bissle KeyWords Spielerei
        upload_video.argparser.add_argument("--privacyStatus",
                                            choices=upload_video.VALID_PRIVACY_STATUSES,
                                            default=upload_video.VALID_PRIVACY_STATUSES[2],  # Grundsätzlich Unlisted
                                            help="Video privacy status.")
        args = upload_video.argparser.parse_args()  # Erstelle ein Objekt mit args und dieses objekt hat obige
        # ... Eigenschaften... so dass man diese über den Punkteoperator abfragen kann.

        if not os.path.exists(args.file):  # Abfrage des Parameters --file über den Punktoperator.
            exit("Please specify a valid file using the --file= parameter.")
        youtube = upload_video.get_authenticated_service(args)  # aus upload_video.py -> google api für YT
        try:
            my_video_id = None
            my_video_id = upload_video.initialize_upload(youtube, args)
            return my_video_id

        except upload_video.HttpError as e:
            print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))

    def download_video_with_youtube_dl(self, yt_link_id, target_path="."):
        """ Downloads the video from a give youtube link id to the specified target folder
        This function does the same as pytube, but instead of throwing errors because of the wrong client header
         youtube_dl does it smooth and without errors... this function should be used.

         python -m youtube_dl -F https://www.youtube.com/watch?v=XXXX
[youtube] XXXX: Downloading webpage
[youtube] XXXX: Downloading video info webpage
[youtube] XXXX: Downloading MPD manifest
[info] Available formats for XXXX:
format code  extension  resolution note
139 m4a        audio only DASH audio   49k , m4a_dash container, mp4a.40.5@ 48k (22050Hz)
140 m4a        audio only DASH audio  130k , m4a_dash container, mp4a.40.2@128k (44100Hz)
251 webm       audio only DASH audio  138k , webm_dash container, opus @160k (48000Hz)
256 m4a        audio only DASH audio  195k , m4a_dash container, mp4a.40.5, 241.59KiB
258 m4a        audio only DASH audio  389k , m4a_dash container, mp4a.40.2, 476.76KiB
278 webm       256x144    DASH video   95k , webm_dash container, vp9, 24fps, video only
160 mp4        256x144    DASH video  108k , mp4_dash container, avc1.4d400b, 24fps, video only
242 webm       426x240    DASH video  220k , webm_dash container, vp9, 24fps, video only
133 mp4        426x240    DASH video  242k , mp4_dash container, avc1.4d400c, 24fps, video only
243 webm       640x360    DASH video  405k , webm_dash container, vp9, 24fps, video only
134 mp4        640x360    DASH video  419k , mp4_dash container, avc1.4d401e, 24fps, video only
244 webm       854x480    DASH video  752k , webm_dash container, vp9, 24fps, video only
135 mp4        854x480    DASH video 1155k , mp4_dash container, avc1.4d4014, 24fps, video only
247 webm       1280x720   DASH video 1505k , webm_dash container, vp9, 24fps, video only
136 mp4        1280x720   DASH video 2310k , mp4_dash container, avc1.4d4016, 24fps, video only
248 webm       1920x1080  DASH video 2646k , webm_dash container, vp9, 24fps, video only
137 mp4        1920x1080  DASH video 3486k , mp4_dash container, avc1.640028, 24fps, video only
43  webm       640x360    medium , vp8.0, vorbis@128k, 940.82KiB
18  mp4        640x360    medium  648k , avc1.42001E, mp4a.40.2@ 96k (44100Hz), 792.54KiB
22  mp4        1280x720   hd720 1734k , avc1.64001F, mp4a.40.2@192k (44100Hz) (best)

         """
        yt_video_filetype = "mp4"  # Nur zur Benennung benötigt, alles andere macht der Format Code 137
        yt_video_format = "1080p"  # Nur zur Benennung benötigt, alles andere macht der Format Code 137

        dateiname = yt_link_id + "_" + yt_video_format + "." + yt_video_filetype
        # Absoluter Zielspeicherort, ansonsten wird die Datei im falschen Ordner gespeichert
        target_filename = os.path.abspath(os.path.join(target_path, dateiname))

        # Quelle:  https://www.bogotobogo.com/VideoStreaming/YouTube/youtube-dl-embedding.php
        # Quelle2: https://github.com/ytdl-org/youtube-dl/blob/master/youtube_dl/YoutubeDL.py#L164
        # Brauche nur Video, soll gespeichert werden im Zielordner, Wenn Link eine Playlist... nur das Video!
        ydl_options = {
            # 'format': 'bestvideo[ext=' + yt_video_filetype + ']',
            'format': '137',  #
            'outtmpl': '' + target_filename + '',
            'noplaylist': True
            # 'format': 'bestvideo[ext=' + yt_video_filetype +']/best[height=1080]'
        }
        youtube_links = ["https://www.youtube.com/watch?v=" + yt_link_id]
        with youtube_dl.YoutubeDL(ydl_options) as ydl_obj:
            ydl_obj.download(youtube_links)

        return dateiname

class QRCrypt:
    def __init__(self, fingerprint_server, privkey_passphrase):
        """ Erstellt ein neues Objekt für das Ver- und Entschlüsseln Nachrichten oder Dateien.
        Klasse wird zum sammeln / Gruppieren der Methoden benötigt...
        Todo: Methoden ggf. als @staticmethod deklarieren

        :param fingerprint_server: Enthält den Fingerprint des zu verwendenen Serverschlüssels.
        :param privkey_passphrase
        """

        self.last_decrypted_data = None  # Wird aus QRCodeManagement heraus benötigt.
        self.last_key_used_for_signature = None  # Wird aus QRCodeManagement heraus benötigt.

        # Pfad für das Zielsystem unbedingt anpassen
        self._gpg = gnupg.GPG(gpgbinary="C:\\Program Files (x86)\\GnuPG\\bin\\gpg.exe")

        # Prüfe auf Vorhandensein aller notwendigen Verzeichnisse und erstelle sie.
        # Wenn nur ein Verzeichnis nicht erstellt werden kann, wird das Programm abgebrochen.
        # all files which are available for tranmission
        self._files_outgoing_available_for_encryption = "files_outgoing_available_for_encryption/"
        # Working directory for encrypting files
        self._files_outgoing_already_encrypted = "files_outgoing_already_encrypted/"
        # Folder where downloaded encryoted files from other senders are found and have not beend decrypted yet
        self._files_incoming_encrypted = "files_incoming_encrypted/"
        # Folder where the gpg file will be stored.
        # The GPG File will be created through decoding all qr codes in the video.
        self._files_incoming_encrypted_analyzed = "files_incoming_encrypted_analyzed/"
        # Folder where decrypted files are stored
        self._files_incoming_decrypted = "files_incoming_decrypted/"
        # Folder for the generated video files. Video Files will have embedded qr codes with encrypted data
        self._files_outgoing_video_encrypted = "files_outgoing_video_encrypted/"

        # The following folders are for challenge/announcement / response qr codes
        # It could be possible to copy / paste the encrypted challenge/announcement and response data directly
        # but it is easier to detect than images. The Choice is up to the user. Both will be created.

        # Folder for the qr code, which content will shows the client the available files being available and
        # the server status (for later livestreaming features)
        # This QR Code can be transmitted over any medium (e.g. Skype, Tox...) because of its encrypted data.
        self._files_announcement_qrcode_from_server = "files_announcement_qrcode_from_server/"
        # Folder in which the client process will put the "file selection" qr code as response to the
        # server announcement qr code. The response QR code will include the user selection of file(s)
        # This QR Code can be transmitted over any medium (e.g. Skype, Tox...) because of its encrypted data.
        self._files_response_qrcode_from_client = "files_response_qrcode_from_client/"

        self._check_and_create_directories()

        # Liste aller Empfänger sind später in dieser Liste / Array für die eine Nachricht / Datei verschlüsselt wird.
        self._recipients_array = []

        # Enthält den Fingerabdruck mit dem die Nachricht signiert werden kann.
        # Dies lässt natürlich Rückschlüsse darauf zu, wer die Nachricht verschlüsselt hat und
        # ist ggf ein Problem in Punkto Sicherheit.
        self._fingerprint_server = fingerprint_server
        self._privkey_passphrase = privkey_passphrase
        self._files_in_dir = []
        self.refresh_files()


    def _check_and_create_directories(self):
        """ Prüft auf Vorhandensein aller notwendigen Verzeichnisse
        und erstelle sie, sofern sie noch nicht existieren """
        self._folder_check_and_create(self._files_outgoing_available_for_encryption)
        self._folder_check_and_create(self._files_outgoing_already_encrypted)
        self._folder_check_and_create(self._files_incoming_encrypted)
        self._folder_check_and_create(self._files_incoming_encrypted_analyzed)
        self._folder_check_and_create(self._files_incoming_decrypted)
        self._folder_check_and_create(self._files_outgoing_video_encrypted)
        self._folder_check_and_create(self._files_announcement_qrcode_from_server)
        self._folder_check_and_create(self._files_response_qrcode_from_client)

    def refresh_files(self):
        self._files_in_dir = []

        files = [f for f in os.listdir(self._files_outgoing_available_for_encryption) if os.path.isfile(f)]
        for f in files:
            self._files_in_dir.append(f)

    def add_recipient(self, recipient):
        """ Fügt einen Empfänger zum recipient Array hinzu.
        This function checks if the recipient is in the keyring and also trusted.
        Otherwise the recipient can not be added to the recipient list.
        """
        # Todo Prüfen ob der recipient in gpg keyring vorhanden ist und ob ihm vertraut wird.
        found = False
        is_trusted = False
        public_keys = self._gpg.list_keys()
        for pubkey in public_keys:
            if recipient in pubkey.values():
                found = True
                if pubkey["ownertrust"] == "u" or pubkey["ownertrust"] == "f":
                    # https://security.stackexchange.com/questions/69062/
                    # what-is-the-difference-between-full-and-ultimate-trust
                    is_trusted = True
                    break  # Key wurde in den Public Keys gefunden. Es kann weitergehen.
        assert found, "The Public Key " + recipient + "was not found in the GnuPG Keyring. Please add the public key " \
                                                      "to it and trust it. Otherwise no communication will be able with this pubkey. "
        assert is_trusted, "The Public Key " + recipient + "was not trusted in the GnuPG Keyring. Please trust  the " \
                                                           "public key (fully or ultimate). Otherwise no " \
                                                           "communication will be able with this pubkey. "

        if recipient in self._recipients_array:
            print(recipient + " ist schon in der Empfängerliste")
        else:
            self._recipients_array.append(recipient)
            print(recipient + " wurde zur Empfängerliste hinzugefügt!")

    def list_openpgp_trusted_pubkeys(self):
        """ This function gets gnupg trusted recipients and gives it back as todo array / dict """
        return self._gpg.list_keys()  # Public Keys

    def get_files_outgoing_available_for_encryption(self):
        return self._files_outgoing_available_for_encryption

    def get_files_outgoing_already_encrypted(self):
        return self._files_outgoing_already_encrypted

    def get_files_incoming_encrypted(self):
        return self._files_incoming_encrypted

    def get_files_outgoing_video_encrypted(self):
        return self._files_outgoing_video_encrypted

    def get_files_announcement_qrcode_from_server(self):
        return self._files_announcement_qrcode_from_server

    def get_files_response_qrcode_from_client(self):
        return self._files_response_qrcode_from_client

    def get_recipients(self):
        return self._recipients_array

    def reset_recipients(self):
        # Setzt die Empfängerliste wieder auf Ursprung zurück.
        # Auch von extern bewusst erreichbar.
        self._recipients_array = []

    def decrypt_text_message(self, message_encrypted, optional_passphrase=""):
        self.last_decrypted_data = None
        self.last_key_used_for_signature = None
        if optional_passphrase == "":
            # Wenn kein anderer Schlüssel angegeben wurde, probiere die Entschlüsselung mit dem Serverschlüssel
            self.last_decrypted_data = self._gpg.decrypt(message_encrypted, passphrase=self._privkey_passphrase)
            assert self.last_decrypted_data.ok,"decrypt_text_message: Die Entschlüsselung war nicht erfolgreich. fehlt die Signatur?"
        else:
            # Entschlüsselung des Private Keys mit der optional_passphrase. Dann Entschlüsselung.
            self.last_decrypted_data = self._gpg.decrypt(message_encrypted, passphrase=optional_passphrase)

        try:
            self.last_key_used_for_signature = self.last_decrypted_data.sig_info[self.last_decrypted_data.signature_id][
                'keyid']
            self.add_recipient(self.last_key_used_for_signature)
            print("(Grund für das hinzufügen: Nachrichtenersteller wird Antwort erhalten)")
        except:  # sofern keine Sig_info vorhanden ist.
            print("decrypt_text_message: Fehler beim Ermitteln des signierenden Schlüssels.")
            last_key_used_for_signature = ""

        assert self.last_key_used_for_signature, "decrypt_text_message: Text message was not signed. This is forbidden!"
        assert self.last_decrypted_data, "decrypt_text_message: No decrypted data available. Error? Please check "
        assert self.last_decrypted_data.trust_level is not None, "Message signature is missing. This is not allowed " \
                                                                 "right now "
        assert self.last_decrypted_data.trust_level >= self.last_decrypted_data.TRUST_FULLY, "Message signature is not trusted. Add the " \
                                                                                             "Key and trust it if you have checked the " \
                                                                                             "fingerprint! Sig_info:\n" + \
                                                                                             str(
                                                                                                 self.last_decrypted_data.sig_info)

        # Nächstes if Statement eigentlich auf Grund der asserts oben drüber hinfällig...
        # wird zum Verständnis gelassen,
        # dass nur vertrauenswürdige Absendernachrichten mit Signaturen akzeptiert weden.
        if self.last_decrypted_data.trust_level is not None and self.last_decrypted_data.trust_level >= self.last_decrypted_data.TRUST_FULLY:
            return str(self.last_decrypted_data)
        else:
            return ""  # nicht signierte und nicht vertrauten Daten wird nicht vertraut.

    def encrypt_text_message(self, message_unencrypted, reset_recipients_after_encryption=False):
        """ This function encrypts for example a textmessage for the recipients which has been added
        to the object via add_recipients method, which checks, if the key is in the keyring and also trusted.
        Communication can only be made between trusted persons.
        If this functions is called and no recipients are in the list
        the program terminates with an assertion error"""

        # Prüfen, ob recipients array leer ist.
        assert self._recipients_array, "No Recipients defined. Add recipients via method: add_recipient"

        # Verschlüssel Nachricht für n Empfänger
        result = self._gpg.encrypt(message_unencrypted,
                                   self._recipients_array,
                                   sign=self._fingerprint_server,
                                   passphrase=self._privkey_passphrase)
        if not result.ok:
            print("ok: ", result.ok)
            print("status: ", result.status)
            print("stderr: ", result.stderr)
        assert result.ok, "Signieren der Nachricht fehlgeschlagen auf Grund falscher Passphrase"

        message_encrypted = str(result)  # Verschlüsselter text

        # Sollten weitere Nachrichten verschlüsselt für gleiche Empfänger verschlüsselt werden?
        if reset_recipients_after_encryption:
            self.reset_recipients()
        return message_encrypted

    def decrypt_file(self, filename, optional_passphrase=""):
        """ This function implements the decryption process for files being sent to the server
        After the files are stored in the Incoming encrypted folder, this function decrypts it and
        saves it to the incoming decrypted folder.
        An Assertion Error Occurs, if the File has no signature or the keys are not trusted, but it can
        """
        source_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                   self._files_incoming_encrypted))
        destination_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                        self._files_incoming_decrypted))

        source_file = os.path.join(source_path, filename)
        assert (filename[-4:] == ".gpg" and len(filename) > 4), "The filename does not end with .gpg " \
                                                                "or has only 4 characters. "
        destination_file = os.path.join(destination_path, filename[0:-4])

        assert os.path.exists(source_file), "decrypt file: Source File " + filename + \
                                            " does not exist in folder " + source_path
        assert os.path.exists(destination_path), "dencrypt file: Destination path does not exist: " + destination_path

        decrypted_data = None
        with open(source_file, "rb") as f:
            # A untrusted File should not be decrypted, because "always_trust" parameter's default value is False
            # https://gnupg.readthedocs.io/en/latest/#decryption
            decrypted_data = self._gpg.decrypt_file(f,
                                                    passphrase=self._privkey_passphrase,
                                                    output=destination_file)
            print("decrypt_file ok: ", decrypted_data.ok)
            print("decrypt_file status: ", decrypted_data.status)
            print("decrypt_file stderr: ", decrypted_data.stderr)
        assert decrypted_data, "decrypt_text_message: No decrypted data available. Error. please Check "
        assert decrypted_data.trust_level is not None, "Message signature is missing. This is not allowed right now"
        assert decrypted_data.trust_level >= decrypted_data.TRUST_FULLY, "Message signature is not trusted. " \
                                                                         "Add the Key and trust it if you have " \
                                                                         "checked the fingerprint! Sig_info:\n" + \
                                                                         str(decrypted_data.sig_info)

        if decrypted_data is None:
            return False
        else:
            return decrypted_data.ok  # Gibt True oder False zurück

    def encrypt_file(self, source_filename, destination_filename, reset_recipients_after_encryption=False):
        """ Encrypts and signs the file with the filename in the folder files_outgoing_available_for_encryption
        The file will be encrypted and signed with the server keys.
        prior calling this function the recipients array must be filled with at least one recipient.
        for this use the method add_recipient.
        After a file was encrypted the recipients for the next encryption stay the same.
        If you want to reset the recipients, so that you can address new targets,
        set the parameter reset_recipients_after_encryption = True

        :param source_filename: Filename of the file which should be encrypted
        :param reset_recipients_after_encryption: If True, the recipients array will be reset after encryption
        :return: status of the encryption as boolean True or False
        """
        # Prüfen, ob recipients array leer ist.
        assert self._recipients_array, "No Recipients defined. Add recipients via method: add_recipient"
        source_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                   self._files_outgoing_available_for_encryption))
        destination_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                        self._files_outgoing_already_encrypted))

        source_file = os.path.join(source_path, source_filename)
        destination_file = os.path.join(destination_path, destination_filename)
        assert os.path.exists(source_file), "encrypt file: Source File " + source_filename + \
                                            " does not exist in folder " + source_path
        assert os.path.exists(destination_path), "encrypt file: Destination path does not exist: " + destination_path

        status = None
        with open(source_file, "rb") as f:
            status = self._gpg.encrypt_file(f, self._recipients_array,
                                            output=destination_file,
                                            passphrase=self._privkey_passphrase,
                                            armor=True,
                                            sign=self._fingerprint_server)
        if reset_recipients_after_encryption:
            self.reset_recipients()

        if status is None:
            return False
        else:
            return status.ok  # Gibt True oder False zurück

    def get_youtube_download_folder(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), self._files_incoming_encrypted))

    @staticmethod
    def _folder_check_and_create(foldername):
        """Helper Function to create a folder in the actual folder of this file
        This mainly addresses the storage of the encrypted and decrypted files of the files to be send or received
        """
        pfad = os.path.abspath(os.path.join(os.path.dirname(__file__), foldername))
        if os.path.exists(pfad):
            print(pfad + " already exists!")
        else:
            try:
                os.mkdir(pfad)
            except OSError:
                print("Creation of the Directory failed: " + pfad)
                print("Please manually create all folders and give sufficient permission please!")
                sys.exit(0)
            else:
                print("Directory successfully created: " + pfad)

class QRCodeManagement:
    """Dient der Verwaltung des Management QR Codes,
    so dass alle Informationen dem Client verfügbar gemacht werden."""

    def __init__(self, pubkey_server_fingerprint="", privkey_passphrase="", version=1):
        # Initialisiere das QRCrypt Objekt. Somit stehen alle Verschlüsselungsaktionen hier zur Verfügung.
        # Könnte auch außerhalb stehen... aber ist im POC nicht notwendig.

        #  Public
        self.cryptobj = QRCrypt(fingerprint_server=pubkey_server_fingerprint,
                                privkey_passphrase=privkey_passphrase)

        self.decryptobj = {}  # Hier wird später die entschlüsselte Nachricht gespeichert.
        self.decryptobj_sender_key = ""  # Hier wird später der Signaturschlüssel der entschlüsselte Nachricht gespeichert.
        self.listen_to_command = True
        self.converting_files = False
        # Gesamtframecounter, der immer hochgezählt wird, wenn ein Frame relevant für FFMPEG-Stream ist
        # Zählt also jeden Frame
        self.lifetime_framecounter = 0
        # In Client Mode: Which Files can the client choose?
        # Will be filled
        self.server_filelist_for_client = []
        self.client_file_or_link_from_response = ""
        # self.last_encrypted_qrcode_content = ""
        self.last_encoded_video_filenames = ""  # Für glob.glob()
        # Link-ID (11-Stellig) mit Empfängern durch leerzeichen getrennt
        # dKtYH7GraMX 00B742790007CXXX BCF5572DEC063XXX
        self.last_youtube_link_with_recipients = ""

        #  Private
        self._active_transmission = False
        # Wird nur für die jeweilige Übertragung hochgezählt
        # Denkbar ist eine Erweiterungen auf n gleichzeitige Übertragungengen.
        # Status dann z.B. "Counter1;Counter2;...Counter(n)\r\n".
        # Ist nicht im POC enthalten!
        self._active_transmission_framecounter = 0
        # Hier wird der "lifetime_framecounter" eingetragen, bei dem die Dateiübertragung der Datei beginnt
        # Nur bei start_transmission
        self._active_transmission_startframe = 0
        # Hier wird der "lifetime_framecounter" eingetragen, bei dem die Dateiübertragung endet.
        # (nur bei stop_transmission)
        # Ist 0 solange die Transmission läuft. Im Frame NACH der Transmission steht hier der Lifetimecounter drin
        self._active_transmission_endframe = 0

        #  Im Standard wird nach einem entsprechenden Unterordner im aktuellen Ordner gesucht.
        pfad = os.path.abspath(os.path.join(os.path.dirname(__file__), "files_outgoing_available_for_encryption"))
        self._path_to_not_encrypted_files = pfad
        self._filelist = []
        self._pubkey_server_fingerprint = pubkey_server_fingerprint
        self._version = version

        self.rebuild_filelist()

    def _increment_frame_counters(self):
        """ Inkrementiert die FrameCounters innerhalb der Lebenszeit des Objektes
        Ohne Managementframe mit der Frameangabe kann man nicht debuggen."""
        # Wenn der Server Befehle entgegennimmt, wird nicht übertragen und umgekehrt
        if self._active_transmission:
            self._active_transmission_framecounter += 1
            self.lifetime_framecounter += 1
        else:
            self.lifetime_framecounter += 1

    def start_transmission(self):
        self._active_transmission = True
        self._active_transmission_startframe = self.lifetime_framecounter
        self._active_transmission_endframe = 0

    def stop_transmission(self):
        """Startet das Zählen der Frames für die Transmission. Die Anzahl der Frames steht im ersten Frame NACH
        der Dateiübertragung im Management QR Code"""
        self._active_transmission = False
        self._active_transmission_endframe = self.lifetime_framecounter  # dort endet die Übertragung.
        # Wird beim nächsten QR-Code angezeigt. Also der Frame nach dem letzten Frame der gestoppte transmission

    def get_qrcode_content(self):
        """Gibt den Content wieder für den jeweils gültigen Management QR Code"""
        separator = "\r\n"
        # separator_inline = ";"
        ausgabe = str(self._version)
        ausgabe += separator
        ausgabe += self._pubkey_server_fingerprint
        ausgabe += separator
        ausgabe += str(int(self.listen_to_command))
        ausgabe += separator
        ausgabe += str(int(self.converting_files))  # Eine Zeile
        ausgabe += separator
        #  Start Framezähler gesamt, und für Dateiübertragungen
        ausgabe += str(self.lifetime_framecounter)
        ausgabe += separator
        ausgabe += str(self._active_transmission_framecounter)
        ausgabe += separator
        ausgabe += str(self._active_transmission_startframe)
        ausgabe += separator
        ausgabe += str(self._active_transmission_endframe)  # Ist 0 solange Frameende nicht bekannt ist.
        ausgabe += separator + separator  # Doppelte neue Zeile

        ausgabe += separator.join(self._filelist)  # Jede Datei in einer neuen Zeile
        ausgabe += separator + separator  # Doppelte neue Zeile
        ausgabe += self.last_youtube_link_with_recipients  # Beispiel: dKtYH7GraMX 00B742790007CXXX BCF5572DEC063XXX
        # ausgabe += str(len(ausgabe))  # Prüfen wie lang es ist...

        return ausgabe


    @staticmethod
    def show_file_in_windows_explorer(filename):
        subprocess.Popen(r'explorer /select,"' + filename + '"')

    def read_encrypted_server_announcement_qr_code(self):
        self.server_filelist_for_client = []
        source_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                   self.cryptobj.get_files_announcement_qrcode_from_server()))
        source_filename = source_path + "\\server_announcement_qr_code.png"
        if os.path.exists(source_filename):
            qrcode_img = cv2.imread(source_filename, 0)
            decodedobjects = QRCodeTools.decode(qrcode_img)
            if decodedobjects:
                message = decodedobjects[0].data.decode('UTF-8')  # der erste Erkannte QRCode wird zurückgegeben.
                if message:
                    decrypted_message = self.decrypt_signed_qrcode_content(message)
                    if decrypted_message:
                        self.server_filelist_for_client = decrypted_message['_filelist']
                        if self.server_filelist_for_client:  # if not empty...
                            try:
                                if not " ".join(decrypted_message['youtube_links']).strip() == "":
                                    self.server_filelist_for_client.append(" ".join(decrypted_message['youtube_links']))
                            except:
                                print("Problem bei den YouTube_Links der decrypted_message")
                            return self.server_filelist_for_client
                            # Für Debugzwecke gelassen
                            # for zaehler, filename_server in enumerate(filenames_list_server):
                            #     print(str(zaehler).zfill(2), filename_server)
                else:
                    print("Error: read_encrypted_server_announcement_qr_code -> message is empty")
            else:
                print("Error: read_encrypted_server_announcement_qr_code -> no qr code detected. White space enough?")
        else:
            print("Error: read_encrypted_server_announcement_qr_code -> Missing file: " + source_filename)

        return self.server_filelist_for_client

    def read_encrypted_client_response_qr_code(self):
        self.client_file_or_link_from_response = ""
        self.decryptobj_sender_key = ""
        source_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                   self.cryptobj.get_files_response_qrcode_from_client()))
        source_filename = source_path + "\\client_response_qr_code.png"
        if os.path.exists(source_filename):
            qrcode_img = cv2.imread(source_filename, 0)
            decodedobjects = QRCodeTools.decode(qrcode_img)
            if decodedobjects:
                message = decodedobjects[0].data.decode('UTF-8')  # der erste Erkannte QRCode wird zurückgegeben.
                if message:
                    decrypted_message = self.decrypt_signed_qrcode_content(message)
                    if decrypted_message:
                        self.client_file_or_link_from_response = decrypted_message
                        # Letzten Signaturschlüssel merken
                        self.decryptobj_sender_key = self.cryptobj.last_key_used_for_signature
                        return self.client_file_or_link_from_response
                else:
                    print("Error: read_encrypted_client_response_qr_code -> message is empty")
            else:
                print("Error: read_encrypted_client_response_qr_code -> no qr code detected. White space enough?")
        else:
            print("Error: read_encrypted_client_response_qr_code -> Missing file: " + source_filename)

        return self.client_file_or_link_from_response

    def write_encrypted_client_response_qr_code(self, filename: str, show_in_explorer=False,
                                                print_encrypted_qrcode_content=False):
        # the encrypted_qrcode_content will automatically be signed by the sender
        # in this POC only one Filename can and should be choosen
        encrypted_qrcode_content = self.cryptobj.encrypt_text_message(filename)
        qrcode_img = generate_qrcode_with_qrcodegen_bib_returns_uint8_v3(encrypted_qrcode_content)
        destination_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                        self.cryptobj.get_files_response_qrcode_from_client()))

        filename = destination_path + "\\client_response_qr_code.png"
        # Todo multiple qr-codes erstellen für 1-n empfänger (auf der server seite über glob einlesen)
        cv2.imwrite(filename, qrcode_img)
        if print_encrypted_qrcode_content:
            print("encrypted qrcode content client response:")
            print(encrypted_qrcode_content)
            print()
            input("Please copy the PGP message as needed. Then press Enter to move on.")
            print()
            print("Encrypted Server Announcement QR Code was saved here: " + filename)

        if show_in_explorer:
            self.show_file_in_windows_explorer(filename)
        return encrypted_qrcode_content

    def write_encrypted_server_announcement_qr_code(self, show_in_explorer=False,
                                                    print_encrypted_qrcode_content=False):
        """ This function creates a server announcement qr code and stores it in the subfolder
        :return: the encrypted content of the server announcement qr code.
        """
        # Encrypted Content with files (and status)
        encrypted_qrcode_content = self.cryptobj.encrypt_text_message(self.get_qrcode_content())
        qrcode_img = generate_qrcode_with_qrcodegen_bib_returns_uint8_v3(encrypted_qrcode_content)
        destination_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                        self.cryptobj.get_files_announcement_qrcode_from_server()))
        filename = destination_path + "\\server_announcement_qr_code.png"
        # Todo multiple qr-codes erstellen für 1-n empfänger

        cv2.imwrite(filename, qrcode_img)
        if print_encrypted_qrcode_content:
            print("encrypted qrcode content server announcement:")
            print(encrypted_qrcode_content)
            print()
            input("Please copy the PGP message as needed. Then press Enter to move on.")
            print()
            print("Encrypted Server Announcement QR Code was saved here: " + filename)

        if show_in_explorer:
            self.show_file_in_windows_explorer(filename)
        return encrypted_qrcode_content

    def decrypt_signed_qrcode_content(self, decoded_qrcode_content: str):
        """ Will decrypt the decoded content of a qr code.
        Should only be used by the client to get information about the serverstatus or available files
        :param decoded_qrcode_content: An encrypted string, which will be decrypted with the private serverkey
        :return: a dictionary with the decrypted
        """
        my_qrcode_infos = {}
        self.decryptobj = None
        self.decryptobj_sender_key = None

        # decrypted_decoded_qrcode_content[0] ist die decrypted message
        # decrypted_decoded_qrcode_content[1] ist der Schlüssel der zum signieren genutzt wurde
        decrypted_decoded_qrcode_content = self.cryptobj.decrypt_text_message(decoded_qrcode_content)
        self.decryptobj_sender_key = self.cryptobj.last_key_used_for_signature

        # decrypted_decoded_qrcode_content == "" evaluiert zu False. alles andere zu True
        if decrypted_decoded_qrcode_content and self.decryptobj_sender_key:
            # Zuerst Status von Dateiliste trennen...
            decrypted_decoded_qrcode_content = decrypted_decoded_qrcode_content.split("\r\n\r\n")
            if len(decrypted_decoded_qrcode_content) >= 2:
                statusinfos = decrypted_decoded_qrcode_content[0].split("\r\n")  # ... dann den Status aufteilen ...
                filelist = decrypted_decoded_qrcode_content[1].split("\r\n")  # ... dann die Dateien aufteilen ...
                youtube_links = decrypted_decoded_qrcode_content[2].split("\r\n")  # ... dann die Dateien aufteilen ...
                if statusinfos[0] == "1":  # Version 1
                    my_qrcode_infos['_version'] = statusinfos[0]
                    my_qrcode_infos['_pubkey_server_fingerprint'] = statusinfos[1]
                    my_qrcode_infos['converting_files'] = statusinfos[2]
                    my_qrcode_infos['lifetime_framecounter'] = statusinfos[3]
                    my_qrcode_infos['_active_transmission_framecounter'] = statusinfos[4]
                    my_qrcode_infos['_active_transmission_startframe'] = statusinfos[5]
                    my_qrcode_infos['_active_transmission_endframe'] = statusinfos[6]
                    my_qrcode_infos['_filelist'] = filelist if filelist else []
                    my_qrcode_infos['youtube_links'] = youtube_links if youtube_links else []
                    self.decryptobj = my_qrcode_infos
                else:
                    print("QRCodeManagement -> decrypt_signed_qrcode_content -> Unknown Status in File")
            elif len(decrypted_decoded_qrcode_content) == 1:  # Anforderung von Datei vom Client
                self.decryptobj = decrypted_decoded_qrcode_content[0]
            else:
                print("QRCodeManagement -> decrypt_signed_qrcode_content -> decrypted_decoded_qrcode_content too small")
        else:
            print("QRCodeManagement -> decrypt_signed_qrcode_content -> decrypted_decoded_qrcode_content is empty ")
        return self.decryptobj

    def encrypt_and_sign_get_qrcode_content(self):
        """In dieser Funktion soll der qrcode_content des Management QR Codes
        für alle Empfänger verschlüsselt werden. NUR Empfänger sind in der Lage des QRCode zu lesen
        Hierfür werden alle Public Keys der autorisierten Empfänger eingelesen
        und der Content für diese n Empfänger verschlüsselt und mit einer Signatur versehen, sofern
        der Funktionsparameter gesetzt ist.
        """
        content_encrypted = self.cryptobj.encrypt_text_message(self.get_qrcode_content())
        assert len(content_encrypted) <= 2211  # Ist ca. die maximale Anzahl an Text, welcher kodiert werden kann
        self._increment_frame_counters()  # Automatisches hochzählen des Frames
        return content_encrypted

    @staticmethod
    def files(path):
        for file in os.listdir(path):
            if os.path.isfile(os.path.join(path, file)):
                yield file  # Gut für Iteration

    def rebuild_filelist(self):
        """Über diese Funktion lässt sich die Dateiliste manuell rebuilden und ist sinnvoll
         sofern man während der Scriptlaufzeit Dateien dem Ordner hinzufügt oder löscht"""
        self._filelist = []  # Leeren
        for file in self.files(self._path_to_not_encrypted_files):
            self._filelist.append(file)  # Dateien im Ordner OpenPGP Anhängen.
        return self._filelist

class QRCodeTools:
    """ Collection of Some QRCode Tools"""

    def __init__(self):
        pass


    @staticmethod
    def decode(imx):
        """ This function finds QR Codes in a picture """
        # Einschränken auf QRCodes!!! Wesentlich schneller!
        decodedobjectsx = pyzbar.decode(imx, symbols=[ZBarSymbol.QRCODE])
        # Nachfolgendes lasse ich zum leichteren Verständnis stehen
        # for obj in decodedobjectsx:
        #     print('Type : ', obj.type),
        #     print('Type : ', obj.rect)
        #     print('Type : ', obj.polygon)
        #     print('Data : ', obj.data)
        return decodedobjectsx

def generate_qrcode_with_qrcodegen_bib_returns_uint8_v3(radix64_chunk, scale=2, border=2):
    """ Generiert ein QR Code als Numpy Array für die Bedürfnisse der 1920x1080 Frameerstellung
    :param radix64_chunk: Die Daten die im QR Code kodiert werden sollen, vorzugsweise in base64/radix64 aufbereitet
    :param scale: Der Skalierungsfaktor für den QRCode.
    :param border: Gibt den Rand um den QR-Code an. Im Normalfall sind es 4 Module. Bei mir nur 2,
    da es sonst mit den 3 QR Codes in der Höhe nicht klappt!
    :return: Numpy Array mit den Abmessungen (border+177+border)*scale
    """
    # Rückgabewert ist ein Numpy Array
    # Im nächsten Schritt wird der base64 / radix 64 kodierte chunk mit niedrigem ECC (ca. 7%) encodiert.
    qr_code_to_generate = qrcodegenmod.QrCode.encode_text(radix64_chunk,
                                                              qrcodegenmod.QrCode.Ecc.LOW)

    qrcode_array_numpy = qr_code_to_generate.get_module_as_numpy(border)

    # Quelle Skalieren mittels Konecker Produkt :
    # https://stackoverflow.com/questions/7525214/how-to-scale-a-numpy-array/29190520
    # Kronecker ist zu langsam beim Skalieren!!!!
    # qrcode_array_numpy = numpy.kron(qrcode_array_numpy, numpy.ones((scale, scale))).astype(
    #     numpy.bool)

    # Skaliert um den Faktor "scale": siehe https://en.wikipedia.org/wiki/Kronecker_product
    # Todo Hier kann die Anzahl der numpy Zugriffe und Zuweisungen reduziert werden...
    qrcode_array_numpy = numpy.repeat(qrcode_array_numpy, scale, axis=0).repeat(scale, axis=1)
    qrcode_array_numpy = numpy.invert(qrcode_array_numpy)  # invertieren
    qrcode_array_numpy = qrcode_array_numpy.astype(numpy.uint8)  # Umwandeln für 8 bit Zahlen (Graustufen-Bild)
    qrcode_array_numpy *= 255  # 00000000 und 11111111
    return qrcode_array_numpy

def erstelle_gesamtframe_v2(framearray_to_split, rows):
    """ Diese Funktion nimmt "framearray_to_split" entgegen und spaltet es in "rows" Anzahl von
    Blöcken und packt dieser untereinander.
    Die Anzahl der Framearrays im framearray_to_split sollten sich durch die Anzahl der Zeilen teilen lassen.
    Das Array in den nächsten drei Zeilen ...
    0123456789ABCDE
    0123456789ABCDE
    0123456789ABCDE

    ...wird mit "split(...,3,axis=1)" zu...
    01234
    01234
    01234
    56789
    56789
    56789
    ABCDE
    ABCDE
    ABCDE

    :param framearray_to_split: Numpy Array, Ist die Menge aller einzelnen QRCodes, die nebeneinander sind.
    :param rows: In wieviele Reihen sollen die QR Codes aufgeteilt werden
    :return: Gibt den Frame zurück, bei dem x QR Codes nebeneinander und rows Reihen untereinander
    """

    # ggf kann man das auch nutzen:
    # teiler = framearray_to_split.shape[1] // rows
    # numpy.vstack((c[:,teiler*0:teiler*1], c[:,teiler*1:teiler*2], c[:,teiler*2:teiler*3]))

    gesplitter_framearray_to_split = numpy.split(framearray_to_split, rows, axis=1)

    for row in range(rows):
        # Leider nicht ander möglich, da numpy sich querstellt, bei allen möglichen stacking Varianten
        # und hierbei verlangt, dass alle Array in der stacking position die gleiche Dimension besitzen
        if row == 0:
            ergebnis_gesamtframe = gesplitter_framearray_to_split[row]
        else:
            ergebnis_gesamtframe = numpy.vstack((ergebnis_gesamtframe,
                                                 gesplitter_framearray_to_split[row]))

    # Am Schluss noch unten und rechts mit Weiß auffüllen, so dass
    # 1080 in der Höhe un
    # 1920 in der Breite erreicht werden
    top_edge = 3  # Oben und ...
    bottom_edge = ergebnis_gesamtframe.shape[0] - 3
    left_edge = 3  # ... unten jeweils drei Pixel entfernen, damit es 1080er Höhe erreichen kann.
    # Stauchung und Streckung von Pixeln führt zu Fehlern in der Analyse!
    right_edge = ergebnis_gesamtframe.shape[1] - 3
    ergebnis_gesamtframe = ergebnis_gesamtframe[top_edge: bottom_edge, left_edge: right_edge]

    if ergebnis_gesamtframe.shape[0] < 1080:  # Todo 1080 dynamisch gestalten
        leer_unten = numpy.full((1080 - ergebnis_gesamtframe.shape[0],
                                 ergebnis_gesamtframe.shape[1]),
                                255,
                                dtype=numpy.uint8)

        ergebnis_gesamtframe = numpy.vstack((ergebnis_gesamtframe, leer_unten))

    if ergebnis_gesamtframe.shape[1] < 1920:  # Todo 1920 dynamisch gestalten
        leer_rechts = numpy.full((ergebnis_gesamtframe.shape[0],
                                  1920 - ergebnis_gesamtframe.shape[1]),
                                 255,
                                 dtype=numpy.uint8)
        ergebnis_gesamtframe = numpy.hstack((ergebnis_gesamtframe, leer_rechts))

    return ergebnis_gesamtframe

# @numba.njit()  # Nicht schneller, sondern mit aktiviertem njit() langsamer Numpy ist startk optimiert!
def fuege_rechts_hinzu_v2(framearray_left, framearray_to_add):
    """ Diese Funktion nimmt das "framearray_to_add" an, welches aus einem QR-Code besteht.
    und fügt es rechts an "framearray_left" an und gibt das Ergebnis wieder zurück.

    :param framearray_left: Das Array an dem das framearray_to_add rechts hinzugefügt werden soll
    :param framearray_to_add: Das rechte Array, was an das linke Array angefügt wird.
    :return: Numpy Array welches die beiden Eingabearrays verknüpft repräsentiert.
    """

    return numpy.hstack((framearray_left, framearray_to_add))

def write_video_file_segment(name, extension, number, dateiinhalt):
    """ Diese Funktion schreibt das Videosegment, welches aus den übergebenen Frames besteht.
    Die Kommentare in dieser Funktion sind aus dem Grund so zahlreich, da es viele Quellen gibt
    aber keine alles komplett beschreibt. Das versuche ich hier nachzuholen...

    :param name: Dateiname ohne Erweiterung der neu zu erstellenden Datei
    :param extension: Die Erweiterung z.B. mp4
    :param number: eine Nummer, die dem Dateinamen hinzugefügt wird.
    :param dateiinhalt: Numpy Array der Dimensionen (Framenummer, Auflösung Y z.B. 1080, Auflösung X z.B. 1920)
    :return: Kein Rückgabewert definiert.
    """
    # YouTube Empfohlene Einstellungen für die Upload-Codierung:
    # https://support.google.com/youtube/answer/1722171?hl=de

    # Umsetzung der Empfohlenen Einstellungen
    # YouTube recommended encoding settings on ffmpeg (+ libx264)
    # Quellen: google: ffmpeg youtube optimal command line options
    # https://gist.github.com/mikoim/27e4e0dc64e384adbcb91ff10a2d3678
    # https://trac.ffmpeg.org/wiki/Encode/YouTube

    # Wichtig: First, don’t try to match YouTube’s output so it won’t re-encode your video; it always re-encodes.
    # YouTube nutzt die Farbübertragungsfunktion ITU-R .BT.709, welcher = sRGB Farbraum ist.
    # ITU-R BT.709 ist für hochauflösendes Fernsehen (HDTV) gedacht. deckt 36% der gesamtsichtbaren Farben ab
    # Helligkeit/Luminanz (wesentlich!) beginnt bei 040 HEX und geht bis 3AC HEX oder Dez 64-940 (10Bit kodiert)
    # bei 8 bit Kodierung (was bei uns Anwendung findet)  gehen Werte von 16-235 (8 zu 10 bit durch anhängen von 2Bit)
    # Schwarz ist also nie ganz schwarz und Weiß ist auch nicht komplett weiß.
    # Außerdem gibt es noch eine Gammakorrektur die eingerechnet wird... WErt hierfür sollte 2,2 sein.
    # (Wahrnehmung der dunklen Bereicher steigt steiler an, als in hellen Bereichen)
    # (Dies begründet auch zum Teil die Fehler bei der KOrrektur später.)
    # Quelle: https://www.hdm-stuttgart.de/~buergel/PDF/ITU-709_Standard.pdf  (!!!GUT!!!!)
    # Quelle: https://kompendium.infotip.de/bt709.html
    # Quelle: https://www.itwissen.info/BTDOT-709-ITU-R-BTDOT-709.html
    # Quelle: http://www.onlinevideo.net/2012/07/how-to-produce-great-looking-video-for-youtube/
    # Quelle: https://scribbleghost.net/2018/10/26/youtube-recommended-encoding-settings-for-ffmpeg/
    # Quelle: https://superuser.com/questions/866798/what-ffmpeg-command-line-matches-the-one-youtube-uses


    # Erklärte Kommandozeile von ffmpeg
    # ffmpeg
    # -i input.ext
    # -movflags +faststart  # Für Ansicht im Webbrowser werden Infos an den Anfang der Datei kopiert,
    #                       # YouTube kann hierdurch den Re-Encoding Prozess starten auch wenn das Video noch nicht
    #                       # vollständig hochgeladen wurde.
    #                       # Quelle: https://trac.ffmpeg.org/wiki/Encode/H.264
    # -c:v libx264      # N x264 codec , wird DEFAULT von ffmpeg genutzt
    # -coder 1          # N CABAC. By DEFAULT CABAC is the entropy encoder used by x264.
    # -preset slow      # X A slower preset will provide better compression, dauert aber länger beim codieren
    # -crf 10           # N Constant Rate Factor: (weglassen, da über quality parameter gesetzt!)
    #                       'quality parameter': 10 erzeugt "-crf 0" bei imageio
    #                       The range of the quantizer scale is 0-51: where 0 is lossless,
    #                       23 is default, and 51 is worst possible. A lower value is a higher quality and a
    #                       subjectively sane range is 18-28. Consider 18 to be visually lossless or nearly so..
    # -c:a aac          # N (nicht benötigt, da kein Sound) -> Audio-Codec
    # -ar 48000         # N (nicht benötigt, da kein Sound) -> Sampling Rate
    # -ac 2             # N (nicht benötigt, da kein Sound) -> Audio Kanäle
    # -profile:v high   # X (High Profile)
    # -level 4.0        # X (gehört zu High Profile)
    # -bf 2             # X ffmpeg standard ist 16 (2 consecutive B frames)
    # -g 15             # X halbe framerate von 30 (Closed GOP. GOP of half the frame rate.) GOP=Group of Pictures
    #                   # GOP = I-Frame -> P-Frame (1-n)-> B-Frame (1-n) <-> I-Frame -> usw.  // I-Frame auch Key-Frame
    #                   # Intra-Coded-Frame --> Predictive coded Frames -> Bidrectional Predictive-code <-> I-Frame
    # -pix_fmt yuv420p  # N chroma subsampling 4:2:0 -> youtube guideline, wird über 'pixelformat': 'yuv420p' gesetzt
    #                   #  Chroma Subsampling / Farbunterabtastung: 4:4:4 Keine Farbunterabstastung / Voller RGB-Raum
    #                   #  Chroma Subsampling / Farbunterabtastung: 4:2:0 Helligkeitswerte komplett / Farbe reduziert
    # -b:v 10M          # X Sets the bitrate to 10Mbps. This is good if the fps is 24,25 or 30.
    #                        Set this to 15M if the video is 48, 50 or 60 fps
    # -threads 4        # N Enables ffmpeg to use 4 threads for multi core CPUs
    # -cpu-used 0       # N Most CPU intensive, but best quality. Uses all cores
    # -r 30             # N nicht benötigt... framerate wird über 'fps': 30 gesetzt
    # -b:a 320k         # N nicht benötigt.... audio bitrate
    # output.ext

    # Beispiel für manuelle Kommandozeile
    # ffmpeg -i <input file> -codec:v libx264 -crf 21 -bf 2 -flags +cgop -pix_fmt yuv420p -codec:a aac -strict -2 -b:a 384k -r:a 48000 -movflags faststart <output_name>.mp4

    # -tune ssim -x264-params subme=0:me="dia"
    # , '-x264-params', 'subme=0:me="dia"']  diese parameter funktioniert nicht, da die mimwrite funktion einen
    # noch nicht gemeldeten Bug besitzt. Der Parameter wird nicht korrekt in die Kommandozeile des FFMPEG Prozesses
    # überegben und  führt zur Beendigung des Prozesses
    # Bemerkung: SSIM=Structural Similarity mit der Option '-tune', 'ssim' herausgenommen,
    # da die Struktuelle Ähnlichkeit zweier Bilder sehr gering sein wird. Ob das Standardverfahren besser ist,
    # bleibt zu testen

    # kargs umfasst die empfohlenen Einstellungen für den Upload nach YouTube.
    # yuv444p kann man zwar nehmen, aber wird von YouTube heruntergerechnet auf yuv420p
    # Besser ist, wenn man bessere Qualität nach YouTube gibt.
    kargs = {'fps': 30,
             # 'pixelformat': 'yuv444p',    # Keine Farbabtastung.
             'pixelformat': 'yuv420p',  # Helligkeit voll, Farbe ist eineschränkt. Sollte ausreichen.
             'quality': 10,
             'macro_block_size': 8,
             'ffmpeg_params': ['-movflags', '+faststart', '-preset:v', 'slow', '-bf', '2', '-g', '15', '-profile:v',
                               'high444']
             }

    dateiname_video = name + str(number).rjust(4, '0') + extension
    print("Schreibe Videodatei: %s" % dateiname_video)
    imageio.mimwrite(dateiname_video, dateiinhalt, **kargs)

def process_verarbeitung(arbeit):
    """ Diese Funktion nimmt ein Array entgegen mit n Zeilen und QR Code Inhalten, welche dann erstellt werden
    Es werden jweweils 15 QR Codes zu einem Frame zusammengebaut und alle Frames dann zu einem Ergebnis Array
    zusammengefügt, welches dann zurückgegeben wird.
    Diese Funktion wird von den Threads genutzt, um die QRCodes zu verarbeiten.

    :param arbeit: Numpy Array mit n Elementen, welche Strings zur QR Code Erstellung enthalten
    :return: Numpy Array vom Shape (n, Zeilen , Spalten), welches n Frames enthält. n = arbeit.shape[0] // 15
    """

    thread_frame_progress = None
    thread_alle_video_frames = None

    for thread_qrcodenummer, qrcodeinhalt in enumerate(arbeit):
        if qrcodeinhalt != "":
            qrcode_matrix = generate_qrcode_with_qrcodegen_bib_returns_uint8_v3(qrcodeinhalt)
        else:
            # Dummy QRCode erstellen,um den Shape zu bekommen. Alternativ: (qrcode_matrix*0)+255), was langsamer ist.
            qrcode_matrix = generate_qrcode_with_qrcodegen_bib_returns_uint8_v3("")
            # Einmalig die Breite des QR-Codes setzen...(Für die Weißen Felder am Schluss
            qrcode_breite = qrcode_matrix.shape[0]
            qrcode_matrix = numpy.full((qrcode_breite, qrcode_breite), 255,
                                       dtype=numpy.uint8)  # Todo 370er Breite/Höhe dynamisch gestalten

        if thread_frame_progress is None:
            thread_frame_progress = qrcode_matrix
        else:
            thread_frame_progress = fuege_rechts_hinzu_v2(thread_frame_progress, qrcode_matrix)

        if (thread_qrcodenummer + 1) % 15 == 0:  # 0-12= 13 Elemente , da bei 0 es anfängt.
            # START - ZENTRALER BESTANDTEIL ZUM FRAMEZUSAMMENBAU
            # aus dem horizontal aneinanderliegenden QRCodes erstelle eine NxM Matrrix durch splitten und umlegen
            thread_neuer_frame = erstelle_gesamtframe_v2(thread_frame_progress, 3)  # Todo 3 Zeilen verallgemeinern
            thread_frame_progress = None  # Zurücksetzen, wenn der Frame fertig ist.

            if thread_alle_video_frames is not None:
                # ReShaping ist notwendig, weil die Frames hintereinander geschrieben werden
                # Form ist dann (Frameanzahl, N , M)
                # Für imagio später benötigt
                thread_alle_video_frames = numpy.append(thread_alle_video_frames,
                                                        numpy.reshape(thread_neuer_frame, (1,
                                                                                           thread_neuer_frame.shape[0],
                                                                                           thread_neuer_frame.shape[
                                                                                               1])),
                                                        axis=0)
            else:
                # ReShaping ist notwendig, weil die Frames hintereinander geschrieben werden
                thread_alle_video_frames = numpy.reshape(thread_neuer_frame, (1, thread_neuer_frame.shape[0],
                                                                              thread_neuer_frame.shape[1]))

    return thread_alle_video_frames

def startup_multithreading(qrm: QRCodeManagement, filename: str):  # TypeHint added
    """ Diese Funktion ist dafür da, die PGP Dateiinhalte zu nehmen, in ein Array zu überführen und
    dabei mittels des QRCode Managements dafür zu sorgen, dass wichtige Frameinformationen verschlüsselt
    als erster QR Code in jedem hinzugefügt werden. Das Array wird auf eine entsprechend definierte Anzahl an
    Workerprozessen übergeben. Dies macht es skalierbar.
    Über den ersten Management QR Code in jedem Frame lässt sich ermitteln, ob Frames geskipped werden.
    Diese könnte man sich dann theoretisch als Client neu anfordern.

    :param filename: Dateiname mit .gpg am Schluss. Wird für quelldatei- und zieldateiname verwendet
    :param qrm: Instanziiertes Objekt aus der Klasse QRCodeManagement, die die Kontrolle über die Inhalte behält
    :return:  target_filename + "*" + ".mp4"  =X, für die Verwendung mit glob.glob(X) zum mergen der Einzelfiles
    """

    source_path_with_encrypted_file = os.path.abspath(
        os.path.join(os.path.dirname(__file__), qrm.cryptobj.get_files_outgoing_already_encrypted()))
    target_path_for_video = os.path.abspath(
        os.path.join(os.path.dirname(__file__), qrm.cryptobj.get_files_outgoing_video_encrypted()))
    source_filename = os.path.abspath(os.path.join(source_path_with_encrypted_file, filename))  # GPG File
    target_filename = os.path.abspath(os.path.join(target_path_for_video, filename))  # MP4 File...
    print("source_filename", source_filename)
    print("target_filename", target_filename + ".mp4")
    # Wenn Datei nicht existiert, dann ist etwas gewaltig schief gegangen. Abbruch.
    assert os.path.exists(source_filename), "startup_multithreading: Filename does not exist." + source_filename

    # Wieviel QRCodes werden in einem Frame dargestellt
    gesamt_qrcodes_pro_frame = 15
    # Jeder Thread / Prozess erhält Daten für 0,5 sek Video zum Berechnen
    # frames_pro_thread = 15
    frames_pro_thread = 30  # Sollte nicht kleiner sein als 15
    # 5 Worker bearbeiten dann bei 15 Frames Arbeitslast einen Umfang von 2,5 Sekunden Video
    # Es ist also in Kombination zu sehen mit der Variablen "frames_pro_thread"
    # erhöht man die Worker auf 10, verkleinert sich der zu bearbeitende Umfang auf die Hälfte
    # deshalb sollte man dann auch die frames_pro_threads verdoppeln.
    num_workers = 10  # Sollte nicht kleiner sein als 5. und nicht höher als die Anzahl der Kerne im Rechner
    # num_workers = 5
    bytes_pro_qrcode = 2100  # Bleiben noch 111 bytes übrig, nutzbar mit ungefähr 10 zeilem mit 10 zeichen + \n
    # max_frames_fuer_video_part = 5 * 30  # 5 Sekunden mal 30 Frames
    while (frames_pro_thread * num_workers) < 5 * 30:
        frames_pro_thread = frames_pro_thread * 2  # Frames pro Thread mind. 150, ansonsten

    # Wird die Zahl in "max_frames_fuer_video_part" zu groß ist der RAM Verbrauch riesig und führt ggf zum Absturz
    max_frames_fuer_video_part = frames_pro_thread * num_workers
    # Videofiles Nummerierung
    video_datei_zaehler = 0

    # Zähler für QRCodes und Frames sind dafür da, um die Daten zu finden und zu organisieren
    # die Initialisierung von numba dauert recht lange und verringert das multiprocessing ergebnis
    # Dehalb sollte oben die Anzahl der zu bereechnenden QRCodes in den Frames nicht zu gering sein.
    qrcodezaehler = 0
    framezaehler = 0

    groesse = 0
    # frame_qrdcodes_zaehler = 0
    # test_numpy = numpy
    qrcodeinhalte = []
    erster_qr_code = True

    with open(source_filename) as grossedatei:
        qrm.start_transmission()
        while True:
            chunk = grossedatei.read(bytes_pro_qrcode)
            # print(chunk)  #
            groesse += len(chunk)
            if not chunk:
                break  # aus der While Schleife raus
            else:
                if not erster_qr_code:
                    qrcodeinhalte.append(chunk)
                    qrcodezaehler += 1  # Zählt die QRCodes im Frame nach oben
                    if qrcodezaehler == gesamt_qrcodes_pro_frame:
                        framezaehler += 1
                        qrcodezaehler = 0  # Zurücksetzen
                        qrcodeinhalte.append(qrm.encrypt_and_sign_get_qrcode_content())  # Füge Mgmt-QRCode hinzu
                        qrcodezaehler += 1  #
                else:
                    # Füge ersten Managemnet QR Code mit verschlüsseltem Content hinzu
                    # Kommunikation nur zwischen vertrauten Partnern, ansonsten wird abgebrochen
                    # Füge Mgmt-QRCode hinzu im 0-ten Frame
                    qrcodeinhalte.append(qrm.encrypt_and_sign_get_qrcode_content())
                    qrcodezaehler += 1
                    qrcodeinhalte.append(chunk)  # den ersten Chunk im 0-ten Frame nicht vergessen!
                    qrcodezaehler += 1
                    erster_qr_code = False
        if qrcodezaehler != 0:  # Im letzten Frame ist mindestens noch ein QR-Code (Mgmt-QRCode)
            framezaehler += 1  # letzten Frame noch zählen

        while gesamt_qrcodes_pro_frame != qrcodezaehler:  # Sicherstellen, dass der Frame "Voll" ist.
            qrcodeinhalte.append("")  # Wird hinterher zu einem leeren (komplett weißem) qrcode
            qrcodezaehler += 1

        qrm.stop_transmission()

        # Jetzt muss man solange leere chunks appenden bis die Zahl durch frames_pro thread teilbar ist,
        # so dass man den letzten Frame bis zu 1 Sekunde Laufzeit ergänzt. Also im worst case
        # sind es 29 Frames a 13 QRCodes
        # Grund hierfür sind die Worker, die jeweils 1 Sekunde Videomaterial erhalten :)
        qrcodezaehler = 0
        if framezaehler % frames_pro_thread != 0:
            qrcodeinhalte.append(qrm.encrypt_and_sign_get_qrcode_content())  # Mindestens den Mgmt-QR-Code setzen
            qrcodezaehler += 1

        while framezaehler % frames_pro_thread != 0:
            qrcodeinhalte.append("")  # Immer an der zweiten Position im Frame
            qrcodezaehler += 1
            if qrcodezaehler == gesamt_qrcodes_pro_frame:
                framezaehler += 1
                qrcodezaehler = 0
                if framezaehler % frames_pro_thread != 0:  # Immer noch nicht 30 Frames zusammen, also...
                    qrcodeinhalte.append(
                        qrm.encrypt_and_sign_get_qrcode_content())  # ... Mindestens den Mgmt-QR-Code setzen
                    qrcodezaehler += 1

    # print("groesse", groesse)  # Summiert die Mengen an verarbeiteten chunk-längen
    # print("framezaehler", framezaehler)
    # Überführung der QR Code INhalte in ein Numpy Array zum besseren Slicen.
    qrcode_content_numpy = numpy.array(qrcodeinhalte)

    # print("qrcode_content_numpy.shape", qrcode_content_numpy.shape)  # Immer 1-D vom Shape (Anzahl der QRCodes, )
    # print("qrcode_content_numpy.size", qrcode_content_numpy.size)  # Immer Anzahl der QRCodes
    # print("qrcode_content_numpy.dtype", qrcode_content_numpy.dtype)  # Immer <U2100
    # Es sind je 30 Frames pro Thread
    # Der Framezähler ergibt sich aus dem Einlesen der Datei. (ggf. Probleme bei großen Dateien)
    # qrcode_content_numpy.shape[0] ist immer ganzzahlig teilbar durch frames_pro_thread
    qrcodeframes_pro_thread = qrcode_content_numpy.reshape(
        (framezaehler // frames_pro_thread, qrcode_content_numpy.shape[0] // (framezaehler // frames_pro_thread)))
    # print("qrcodeframes_pro_thread.shape", qrcodeframes_pro_thread.shape)  # Immer 2-D. Shape (Anzahl Threads zu
    # bedienen, Anzahl QRCodes z.B. 390 = 13*30)

    # Erste Dimension:  131 Threads, die zu bedienen sind.
    # Zweite Dimension: 390 QRCodes je Thread, die abzuarbeiten sind. 13 Daten QRCodes * 30 Frames
    # Die Management und Steuer-QRCodes werden im Thread berechnet.
    # Hierfür wird die Threadnummer als Teilbereich beim Multiprocessing übergeben. Position ist dann:
    # FRAME = Threadnummer * 390 + (QRCODENUMMER // 13)
    # QRCODE im FRAME = QRCODENUMMER % 13
    # (Rückgabe ist immer ein (numpy) Array mit 30 Frames.)
    # (Diese werden dann zu je 5 Sekunden zusammengestellt und weggeschrieben oder direkt gestreamt.)
    # print(qrcodeframes_pro_thread[0, 0])

    # print("qrcodeframes_pro_thread.shape", qrcodeframes_pro_thread.shape)  # (131, 390).... 131 thread mit 390
    # qrcodes. bei 30 F pro T ode (261,195) bei 15 F pro T

    # Hier erstelle ich das "Aufgaben-Array" für die Threads,
    # welches ein Teil des qrcodeframes_pro_thread Arrays (mit den Inhalten ist
    anzahl_zeilen = qrcodeframes_pro_thread.shape[0]
    # https://stackoverflow.com/questions/54724050/using-numpy-array-split-to-get-desired-split-size-that-is-not-a-sub-multiple
    splitpositions = list(range(num_workers, anzahl_zeilen, num_workers))
    # print("splitpositions", splitpositions)
    frames_von_allen_workern = None
    split_result = numpy.array_split(qrcodeframes_pro_thread,
                                     splitpositions)  # Erstelle ein Array mit um die Threads zu versorgen.
    start = time.time()
    print("Start", start)
    thread = None
    for nummer, element in enumerate(split_result):
        # Nummer ist der Zähler für die Elementarrays in denen z.B. 5 Threads mit je 195 QRCodes versorgt werden
        print(nummer, element.shape)
        # in element.shape[0] sind die Anzahl der Worker. Das letzte Element kann weniger Worker haben!
        with multiprocessing.Pool(processes=element.shape[0]) as pool:
            # Element enthält je n Zeilen mit "frames_pro_thread" Anzahl QRCodes für n Worker. schöööön gleichmäßig
            results = pool.map(process_verarbeitung, element)
        for i, item in enumerate(results):
            if frames_von_allen_workern is None:
                # z.B. die ersten 15 Frames des ersten Threadsresults
                frames_von_allen_workern = item
            else:
                frames_von_allen_workern = numpy.concatenate((frames_von_allen_workern, item), axis=0)
                # print("frames_von_allen_workern.shape", frames_von_allen_workern.shape)

        # (5, 15, 1080, 1920)
        # (5 Threads, 15 Frames kommen zurück, Auflösung X, Auflösung Y)
        # print("numpy.array(results).shape", numpy.array(results).shape)
        print("Verarbeitungstatus:  ", nummer, anzahl_zeilen // num_workers, time.time() - start)
        print("frames_von_allen_workern.shape[0] ", frames_von_allen_workern.shape[0])
        print("max_frames_fuer_video_part", max_frames_fuer_video_part)

        # Todo : Kommt zu Problemen, ggf dann mit >= arbeiten. Dann ist aber das Video u.U. größer als 5 sek.
        # Todo: Dürfte aber auch ggf. kein PRoblem darstellen.
        if frames_von_allen_workern.shape[0] == max_frames_fuer_video_part:
            # write_video_file_segment(dateiname, ".mp4", video_datei_zaehler, frames_von_allen_workern)
            if thread is not None:
                thread.join()  # Nicht zwei Threads mit Schreibzugriffen auf Platte laufen lassen
            thread = threading.Thread(target=write_video_file_segment,
                                      args=(target_filename, ".mp4", video_datei_zaehler, frames_von_allen_workern))
            thread.setDaemon(True)
            thread.start()
            # write_video_file_segment(dateiname, ".mp4", video_datei_zaehler, frames_von_allen_workern)
            video_datei_zaehler += 1  # hochzählen
            frames_von_allen_workern = None
            print("Verarbeitungstatus:  ", nummer, anzahl_zeilen // num_workers, time.time() - start)

    if frames_von_allen_workern is not None:  # den letzten Rest noch wegschreiben!
        thread = threading.Thread(target=write_video_file_segment,
                                  args=(target_filename, ".mp4", video_datei_zaehler, frames_von_allen_workern))
        thread.start()
        video_datei_zaehler += 1  # hochzählen
        # frames_von_allen_workern = None  # nicht notwendig... auskommentiert aber sinnvoll für das Verständnis
        print("Verarbeitungstatus:  ", nummer, anzahl_zeilen // num_workers, time.time() - start)
    if thread is not None:
        thread.join()  # Warten bis die letzte Datei ordentlich geschrieben worden ist.
    return target_filename + "*" + ".mp4"  # Rückgabe des Globparameters zum späteren zusammenfügen aller Dateien

###################################
# --------------------------------#
# ------------MENÜ ---------------#
# --------------------------------#
###################################

def menue_v2(qrm):
    while True:
        print("")
        eingabe = input("Client (1) oder Server (2) oder beenden (99): ")
        try:
            eingabe = int(eingabe)
            if eingabe == 99:
                sys.exit(0)
            if eingabe == 1:
                menue_v2_clientmodus(qrm)
            if eingabe == 2:
                menue_v2_servermodus(qrm)
        except ValueError:
            print("Bitte eine Zahl eingeben.")

# Für Server sowie Clients
def menue_v2_empfaenger_list_trusted_public_keys(qrm):
    trusted_public_keys = []
    print("Nr_|_KEYID____________|_FINGERPRINT______________________________|_UID__________")
    nummer = 0
    for pubkey in qrm.cryptobj.list_openpgp_trusted_pubkeys():  # https://gnupg.readthedocs.io/en/latest/
        if pubkey["ownertrust"] == "u" or pubkey["ownertrust"] == "f":
            print(str(nummer).zfill(2) + "_|_" + pubkey["keyid"] + " | " + pubkey["fingerprint"] + " | " + str(
                pubkey["uids"]))
            trusted_public_keys.append(pubkey["keyid"])  # zur eventuellen Weiterverarbeitung
            nummer += 1
    return trusted_public_keys

def menue_v2_clientmodus(qrm):  # Anzeige Optionen, Eingabe und Auswertung trennen
    eingabe = ""
    while eingabe == "":
        print("")
        print("Client-Modus")
        print("============")
        print("0) Empfänger zurücksetzen")  # ERLEDIGT
        # Trusted Public Keys anzeigen und einen auswählen.
        print("1) Dateiempfänger bzw Nachrichtenempfänger (z.B. Server PublicKey) festlegen ")  # ERLEDIGT
        print("2) Nachrichten senden                (Client Response erstellen)")  # ERLEDIGT
        print("3) Nachrichten empfangen / auswerten (Server Challenge einlesen)")  # ERLEDIGT
        print("4) Datei senden / uploaden an Server über YouTube senden (Wechsel in Server Modus als Client->Punkt  4)")
        print("                           (= Bearbeitungspipeline 1 (BP1) ENCRYPT ENCODE UPLOAD)")  # ERLEDIGT
        print("5) Datei empfangen         (= Bearbeitungspipeline 2 (BP2) DOWNLOAD DECODE DECRYPT)")
        print("")
        print(
            "6) Enkodiertes Videos zusammenfügen und hochladen (vorher Punkt 4 erledigen)")  # abfragen von qrm.last_encoded_video_filenames
        print("7) Empfangenes Video dekodieren und in PGP Datei speichern")
        print("8) PGP Datei entschlüsseln")
        print("")
        print(
            "BP 1: Verschlüssel Datei für Empfänger 1-n -> Enkodiere Daten als Video mit QR Codes -> Upload nach YouTube")
        print("BP 2: Lade Datei von YouTube herunter -> Dekodiere Video mit Frames und QR Codes -> Decrypt PGP File")
        print("")
        print("888) Direkt in den Server-Modus wechseln")
        print("999) Programm beenden")
        eingabe = input("Ihre Auswahl: (99 zum Hauptmenü) ")
        try:
            eingabe = int(eingabe)
            if eingabe == 99:
                break
            else:
                menue_v2_clientmodus_eingabe_auswertung(qrm, eingabe)
                eingabe = ""  # Explizit 99 zum verlassen. Ansonsten loop-en
        except ValueError:  # Kein Int -> nochmal von vorne!
            eingabe = ""

def menue_v2_clientmodus_eingabe_auswertung(qrm, eingabe):  # Anzeige Optionen, Eingabe und Auswertung trennen
    if eingabe == 0:  # 0) Empfänger zurücksetzen
        qrm.cryptobj.reset_recipients()
        print("Empfänger wurden zurückgesetzt!")  # Todo Logging
    elif eingabe == 1:  # Empfänger festlegen
        menue_v2_client_oder_server_empfaenger_auswaehlen(qrm)
    elif eingabe == 2:  # Client Response erstellen
        # Prüfen ob Server Challenge schon eingelesen wurde. Falls nein. Server-Challenge einlesen
        if qrm.server_filelist_for_client:  # Darin sind die Dateien gespeichert, die aus der Challenge stammen
            print("Dateiliste schon vorhanden... Auswahl der Dateien anzeigen")
            menue_v2_clientmodus_server_challenge_auswahl_empfaenger(qrm)
        else:  # Es wurde noch keine Server Challenge eingelesen, jetzt machen (automatisch oder manuell)
            print("Noch keine Dateien vorhanden... Versuche die Server Challenge einzulesen")
            menue_v2_clientmodus_server_challenge_einlesen(qrm)
        if not qrm.server_filelist_for_client:
            print("Error: Keine Dateien in der Server Challenge vorhanden!")
    elif eingabe == 3:  # Server Challenge einlesen
        # Manuell einlesen (oder automatisch) einlesen.
        menue_v2_clientmodus_server_challenge_einlesen(qrm)
    elif eingabe == 4:  # Datei senden -> Wechsel in der Server Modus -> Punkt 4 aufrufen.
        # kein automatischer Aufruf sondern manuelle Abarbeitung
        if not qrm.cryptobj.get_recipients():  # kein Empfänger = Aufruf von Punkt 1
            menue_v2_clientmodus_eingabe_auswertung(qrm, 1)
        else:
            # Empfänger sind vorhanden.
            # In "menue_v2_servermodus_datei_senden" ist die Abfrage nach der Datei, die hochgeladen werden soll.
            menue_v2_servermodus_datei_senden(qrm)
    elif eingabe == 5:  # Datei empfangen
        # Ermitteln der YouTube URL aus der Server Challenge und Download der Datei
        # TODO: 1. Server Challenge erweitern um die YouTube URLs + Empfänger Public Keys in den Dateinamen
        # Todo mit parameter dann aufrufen!
        menue_v2_client_oder_server_datei_video_empfangen(qrm)
    elif eingabe == 6:
        menue_v2_servermodus_eingabe_auswertung(qrm, 6)
    elif eingabe == 7:  # Video dekodieren und in PGP Datei speichern.
        menue_v2_decode_video(qrm)
    elif eingabe == 888:
        menue_v2_servermodus(qrm)
    elif eingabe == 999:
        sys.exit(0)  # Prgoramm beenden
    else:
        # todo funktionsname in print anweisung dynamisch gestalten.
        print("menue_v2_clientmodus_eingabe_auswertung: Not implemented ")

def menue_v2_decode_video(qrm):
    source_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               qrm.cryptobj.get_files_incoming_encrypted()))
    video_dateien = find_files(source_path, "*.mp4")
    if video_dateien:  # im Ordner files_outgoing_video_encrypted
        while True:
            print("Nr | Dateiname")
            for dateizaehler, dateiname in enumerate(video_dateien):
                # os.path.basename(dateiname) holt den Dateinamen aus dem kompletten Pfad mit Datei
                print(str(dateizaehler).zfill(2) + "   " + os.path.basename(dateiname))

            auswahl = input("Bitte wählen Sie eine der vorhandenen Dateien aus (99 zum Abbrechen): ")
            try:
                auswahl = int(auswahl)
                if auswahl == 99:
                    print("Verlasse Dateiauswahl Menü...")
                    break
                if 0 <= auswahl < len(video_dateien):
                    print(video_dateien[auswahl] + " ausgewählt... betrete Analyse...")
                    failed_qrcodes = analyze_video.analyze_video(video_dateien[auswahl],
                                                                 video_dateien[auswahl][0:-4] + ".pgp")
                    print(failed_qrcodes)
                else:
                    print("auswahl", auswahl)
                    auswahl = ""  # Explizit 99 zum verlassen. Ansonsten loop-en
            except ValueError:  # Kein Int -> nochmal von vorne!
                auswahl = ""
    else:
        print("keine passenden Dateien zum Uploaden vorhanden")

def menue_v2_client_oder_server_datei_video_empfangen(qrm):
    # Funktion wird aufgerufen, wenn Client oder Server ein Video herunterladen möchte
    while True:
        print("")
        print("Beispiel 1 Youtube URL:                https://youtu.be/dQw4w9WgXcQ ")
        print("Beispiel 2 Youtube URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ ")
        print("Beispiel 3 Youtube ID:                                  dQw4w9WgXcQ ")
        eingabe = str(input("Bitte die Youtube URL ODER die Youtube ID eingeben (99 zum Abbrechen): "))
        if eingabe == "99":
            break
        else:
            try:
                linkid = ""
                youtube_pos = -1
                youtube_pos = eingabe.find("youtu.be")  # Beispiel 1 (siehe oben)
                if youtube_pos > 0:
                    linkid = eingabe[(youtube_pos + 9):]
                youtube_pos = eingabe.find("?v=")  # Beispiel 2 (siehe oben)
                if youtube_pos > 0:
                    linkid = eingabe[(youtube_pos + 3):]  # ?v=  überspringen
                if linkid == "":  # Falls bis jetzt noch nichts gefudnen wurde...
                    linkid = eingabe

                # Rest nach der YoutubeID abschneiden (geht auch besser... aber das tut's)
                if linkid.find("/") > 0:
                    linkid = linkid[:linkid.find("/")]  # Falls nach der YouTube ID noch / oder ? erscheinen, filtern
                if linkid.find("?") > 0:  # z.B. Zeitangaben...
                    linkid = linkid[:linkid.find("?")]  # Falls nach der YouTube ID noch / oder ? erscheinen, filtern

                linkid = linkid.strip()  # Leerzeichen entfernen.
                if len(linkid) == 11:  # Die Länge der YouTube ID ist IMMER 11 zeichen lang.
                    # Verbesserung möglich, da nur bestimmte Zeichen möglich sind... im POC ignoriert.
                    print("Ermittelte LinkID: " + linkid)
                    ytu = YT()
                    download_folder = qrm.cryptobj.get_youtube_download_folder()
                    # Tut, was es tun soll... herunterladen des Videos in den entsprechenden Ordner
                    print("Versuche Video " + linkid + " nach " + download_folder + " herunterzuladen")
                    ytu.download_video_with_youtube_dl(linkid, download_folder)
                else:
                    print("Ermittelte LinkID: " + linkid)
                    print("Diese YouTube ID hat nicht die Länge 11. Bitte YouTube ID prüfen oder Abbrechen mit 99")

            except:  # Kein Int -> nochmal von vorne!
                print("menue_v2_client_oder_server_datei_video_empfangen: Irgendein Fehler ist aufgetreten")

def menue_v2_client_oder_server_empfaenger_auswaehlen(qrm):  # Menüpunkt 1
    while True:
        print("")
        trusted_public_keys = menue_v2_empfaenger_list_trusted_public_keys(qrm)
        print("")
        eingabe = input("Welcher Key soll als Empfänger hinzugefügt werden? Bitte Nummer eingeben: (99 zum Abbrechen) ")
        try:
            eingabe = int(eingabe)
            if eingabe == 99:
                break  # Aus Menü rausgehen.
            elif 0 <= eingabe < len(trusted_public_keys):
                # Einen noch NICHT in der Liste der Empfänger vorhanden Key hinzufügen.
                # Fügt dem aktuellen cryptobjekt einen Recipient hinzu.
                qrm.cryptobj.add_recipient(trusted_public_keys[eingabe])
                del eingabe
            else:
                print("Bitte ein Element aus der Liste auswählen.")  #
        except (ValueError, TypeError):  # Kein Int -> nochmal von vorne!
            print("Bitte ein Element aus der Liste auswählen.")

def menue_v2_clientmodus_server_challenge_einlesen(qrm):  # Menüpunkt 2 und 3
    # Zuerst versuchen automatisch einzulesen.
    # Wenn das fehlschlägt, die Möglichkeit geben, die Server Challenge zu pasten
    if qrm.read_encrypted_server_announcement_qr_code():
        # An dieser Stelle hat das automatische Einlesen funktioniert
        # und die Liste befindet sich in qrm.server_filelist_for_client
        print("Einlesen des Server Challenge QR Code...")
        menue_v2_clientmodus_server_challenge_auswahl_empfaenger(qrm)
    else:
        # An dieser Stelle hat das automatische Einlesen NICHT funktioniert...
        # manuelle Eingabe antriggern
        print("")
        menue_v2_clientmodus_server_challenge_manual_input(qrm)

def menue_v2_clientmodus_server_challenge_auswahl_empfaenger(qrm):  # Menüpunkt 2
    while True:
        print("")
        print("The following files are available on the server. Please Choose: ")
        print("Nr  Filename")
        for filenumber, filename in enumerate(qrm.server_filelist_for_client):
            print(str(filenumber).zfill(2) + " " + filename)
        eingabe = input("Please choose filenumber: (99 to cancel)")
        try:
            eingabe = int(eingabe)
            if 0 <= eingabe < len(qrm.server_filelist_for_client):
                # Print encrypted content and create client response qr code
                # qrm.last_encrypted_qrcode_content = qrm.write_encrypted_client_response_qr_code(
                qrm.write_encrypted_client_response_qr_code(
                    qrm.server_filelist_for_client[eingabe],
                    show_in_explorer=True,
                    print_encrypted_qrcode_content=True)
            elif eingabe == 99:
                break  # Zurückspringen ins Hauptmenü
            else:
                print("Please choose a valid filenumber!")
        except ValueError:  # Kein Int -> nochmal von vorne!
            print("Please choose a valid filenumber!")

def menue_v2_clientmodus_server_challenge_manual_input(qrm):
    print("")
    # # Quelle: https://stackoverflow.com/questions/30239092/how-to-get-multiline-input-from-user
    print("Please paste the Server Challenge PGP Message. Ctrl-D (linux) or Ctrl-Z (windows) to save it.")
    server_challenge = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        server_challenge.append(line)
    server_challenge = "\r\n".join(server_challenge)
    server_challenge = server_challenge.strip()

    if server_challenge.find("BEGIN PGP MESSAGE") > 0 and server_challenge.find("END PGP MESSAGE") > 0:
        decrypted_message = qrm.decrypt_signed_qrcode_content(server_challenge)
        if decrypted_message:
            # Speichere die Dateiliste für später
            qrm.server_filelist_for_client = decrypted_message['_filelist']
            menue_v2_clientmodus_server_challenge_auswahl_empfaenger(qrm)
            # Dateiliste nun gefüllt... gehe zur Auswahl
        else:
            print("Error: no decrypted message available, so no files")
    else:
        print("Could not find BEGIN PGP MESSAGE or END PGP MESSAGE in the pasted string")

def menue_v2_servermodus(qrm):
    eingabe = ""
    while eingabe == "":
        print("")
        print("Server-Modus")
        print("============")
        print("0) Empfänger zurücksetzen")  # ERLEDIGT
        # Trusted Public Keys anzeigen und einen auswählen.
        print("1) Dateiempfänger bzw Nachrichtenempfänger (z.B. Client PublicKeys) festlegen")  # ERLEDIGT
        print("2) Nachrichten senden        (Server Challenge erstellen)")
        print("3) Nachrichten empfangen     (Client Response einlesen)")
        print(
            "4) Datei senden bzw Empfangsliste abarbeiten (= Bearbeitungspipeline 1 (BP1) ENCRYPT ENCODE UPLOAD)")  # ERLEDIGT
        print("   Empfangsliste abarbeiten: Dateien mit meisten Empfängern zuerst abarbeiten mit BP1")
        print("5) Datei empfangen         (= Bearbeitungspipeline 2 (BP2) DOWNLOAD DECODE DECRYPT)")  # ERLEDIGT
        print("")
        print(
            "6) Enkodiertes Videos zusammenfügen und hochladen (vorher Punkt 4 erledigen)")  # abfragen von qrm.last_encoded_video_filenames
        print("7) Empfangenes Video dekodieren und in PGP Datei speichern")
        print("8) PGP Datei entschlüsseln")
        print("")
        print(
            "BP 1: Verschlüssel Datei für Empfänger 1-n -> Enkodiere Daten als Video mit QR Codes -> Upload nach YouTube")
        print("BP 2: Lade Datei von YouTube herunter -> Dekodiere Video mit Frames und QR Codes -> Decrypt PGP File")
        print("")
        print("888) Direkt in den Client-Modus wechseln")
        print("999) Programm beenden")
        eingabe = input("Ihre Auswahl: (99 zum Hauptmenü) ")
        try:
            eingabe = int(eingabe)
            if eingabe == 99:
                print("Verlasse Server-Modus Menü...")
                break
            else:
                menue_v2_servermodus_eingabe_auswertung(qrm, eingabe)
                eingabe = ""  # Explizit 99 zum verlassen. Ansonsten loop-en
        except ValueError:  # Kein Int -> nochmal von vorne!
            eingabe = ""

def menue_v2_servermodus_eingabe_auswertung(qrm, eingabe):
    if eingabe == 0:  # 0) Empfänger zurücksetzen
        qrm.cryptobj.reset_recipients()
        print("Empfänger wurden zurückgesetzt!")
    elif eingabe == 1:  # Empfänger festlegen
        menue_v2_client_oder_server_empfaenger_auswaehlen(qrm)
    elif eingabe == 2:  # Server Challenge erstellen
        if qrm.cryptobj.get_recipients():
            qrm.write_encrypted_server_announcement_qr_code(show_in_explorer=True, print_encrypted_qrcode_content=True)
        else:
            print("Es existieren noch keine Empfänger. Jetzt festlegen...")
            menue_v2_servermodus_eingabe_auswertung(qrm, 1)
    elif eingabe == 3:  # Client Response einlesen
        # Manuell einlesen (oder automatisch) einlesen.
        menue_v2_servermodus_client_response_einlesen(qrm)

    elif eingabe == 4:  # Datei senden (kann auch aus Client Bereich kommen -> Punkt 4)
        # kein automatischer Aufruf sondern manuelle Abarbeitung im POC
        if not qrm.cryptobj.get_recipients():  # kein Empfänger = Aufruf von Punkt 1
            menue_v2_servermodus_eingabe_auswertung(qrm, 1)
        else:
            # Empfänger sind vorhanden.
            # In "menue_v2_servermodus_datei_senden" ist die Abfrage nach der Datei, die hochgeladen werden soll.
            menue_v2_servermodus_datei_senden(qrm)
    elif eingabe == 5:  # Datei empfangen
        # Ermitteln der YouTube URL aus der Server Challenge und Download der Datei
        # TODO: 1. Server Challenge erweitern um die YouTube URLs + Empfänger Public Keys in den Dateinamen
        menue_v2_client_oder_server_datei_video_empfangen(qrm)
    elif eingabe == 6:  # Video zusammenfügen und hochladen
        video_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                  qrm.cryptobj.get_files_outgoing_video_encrypted()))
        # qrm.last_encoded_video_filenames = "Beispiel.xlsx['<KeyID-1>',
        # '<KeyID-2>'].gpg*.mp4"
        if not qrm.last_encoded_video_filenames == "":
            print()
            print("Passende Dateien zuletzt enkodiertem Video: " + qrm.last_encoded_video_filenames)
            filter_for_files = qrm.last_encoded_video_filenames
            # Die Brackets müssen gefiltert werden mit denen man die PubKeys im Dateinamen ersichtlich macht
            filter_for_files = filter_for_files.replace('[', '[[]')
            passende_dateien = find_files(video_path, filter_for_files)
        else:
            print("Es wurde noch kein Video in der laufenden Session kodiert.")
            # Hier könnte noch evtl. ein Empfängerfilter gebaut werden mit get_recipients()
            passende_dateien = find_files(video_path, "*.mp4")

        if passende_dateien:  # im Ordner files_outgoing_video_encrypted
            while True:
                print("Nr | Dateiname")
                for dateizaehler, dateiname in enumerate(passende_dateien):
                    # os.path.basename(dateiname) holt den Dateinamen aus dem kompletten Pfad mit Datei
                    print(str(dateizaehler).zfill(2) + "   " + os.path.basename(dateiname))

                auswahl = input("Bitte wählen Sie eine der vorhandenen Dateien aus (99 zum Abbrechen): ")
                try:
                    auswahl = int(auswahl)
                    if auswahl == 99:
                        print("Verlasse Dateiauswahl Menü...")
                        break
                    if 0 <= auswahl < len(passende_dateien):
                        print(passende_dateien[auswahl] + " ausgewählt... betrete YouTube Upload Chain...")
                        menue_v2_servermodus_upload_to_youtube(qrm, passende_dateien[auswahl])
                    else:
                        print("auswahl", auswahl)
                        auswahl = ""  # Explizit 99 zum verlassen. Ansonsten loop-en
                except ValueError:  # Kein Int -> nochmal von vorne!
                    auswahl = ""
        else:
            print("keine passenden Dateien zum Uploaden vorhanden")

    elif eingabe == 888:
        menue_v2_clientmodus(qrm)
    elif eingabe == 999:
        sys.exit(0)  # Prgoramm beenden
    else:
        # todo funktionsname in print anweisung dynamisch gestalten.
        print("menue_v2_clientmodus_eingabe_auswertung: Not implemented ")

def menue_v2_servermodus_upload_to_youtube(qrm, video_filename):
    ytu = YT()  # YouTubeUpload Objekt
    video_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                              qrm.cryptobj.get_files_outgoing_video_encrypted()))
    video_path = os.path.abspath(os.path.join(video_path, video_filename))
    if os.path.exists(video_path):
        try:
            # Dies ist der Dateiname als Titel
            title = str(os.path.basename(video_filename)).split("[")[0]
            # Dies sind alle Empfänger in der Beschreibung
            description = str(os.path.basename(video_filename)).split("[")[1].split("]")[0]
            print("YouTube Video Titel: " + title)
            print("YouTube Video Beschreibung: " + description)
            entscheide = input("Wirklich die Datei " + video_filename + "hochladen? (J/j/Y/y/N/n)")
            if entscheide.lower() == "j" or entscheide.lower() == "y":
                print("Datei wird hochgeladen...")
                # mytitle="Test Title", mydescription="Test Description"

                video_id = ytu.upload_video(video_path, mytitle=title, mydescription=description)
                print("Datei wird hochgeladen... Abgeschlossen!")
                print("Die Video-ID lautet:" + video_id)
                print("Zugriff über https://www.youtube.com/watch?v=" + video_id)
                # Todo letzten Upload in die Server Challenge mit aufnehmen
                qrm.last_youtube_link_with_recipients = video_id + " " + " ".join(qrm.cryptobj.get_recipients())
                # Jetzt nur noch die Server Status QR Code erstellen, so dass dieser dem Client übermittelt werden kann.
                menue_v2_servermodus_eingabe_auswertung(qrm, 2)
            else:
                print("Upload des Videos abgebrochen.")
        except IndexError:
            print("Datei kann nicht verwendet werden, da keine [] im Dateinamen vorhanden sind!")
    else:
        print("menue_v2_servermodus_upload_to_youtube: Folgende Datei existiert nicht: " + video_path)

def menue_v2_servermodus_client_response_einlesen(qrm: QRCodeManagement):
    # Manuell einlesen (oder automatisch) einlesen.
    print("Einlesen des Client Response QR Code...")
    ergebnis = qrm.read_encrypted_client_response_qr_code()
    if ergebnis:  # Todo if ergebnis ist richtig... nur debug aktuell
        # es ist etwas in der Client Respone enthalten, nun auswerten
        # Todo Schauen, ob die angforderte Datei existiert oder es mit https (YouTube Video) anfängt
        # Todo Entsprechend dem Empfänger in eine Liste hinzufügen... (erweitern des qrm objekts)
        print("Folgendes wurde anfordert: " + str(ergebnis))
        qrm.cryptobj.add_recipient(qrm.decryptobj_sender_key)
        print("Signierender Schlüssel: " + qrm.decryptobj_sender_key + " als Empfänger hinzugefügt...")
        menue_v2_servermodus_datei_senden(qrm)
    else:
        print("Keine Client Response Informationen im QR-Code. Manuelles Einlesen starten...")
        ergebnis = menue_v2_servermodus_client_response_manual_input(qrm)  # Getestet, funktioniert.
        if ergebnis:
            print("Folgendes wurde angefordert: " + str(ergebnis))
            qrm.cryptobj.add_recipient(qrm.decryptobj_sender_key)
            print("Signierender Schlüssel: " + qrm.decryptobj_sender_key + " als Empfänger hinzugefügt...")
            menue_v2_servermodus_datei_senden(qrm)
        else:
            print("Fehler: menue_v2_servermodus_client_response_manual_input: manuelle Eingabe nicht korrekt")

def menue_v2_servermodus_client_response_manual_input(qrm: QRCodeManagement):  # Todo machen.
    print("")
    # # Quelle: https://stackoverflow.com/questions/30239092/how-to-get-multiline-input-from-user
    print("Please paste the Client Response PGP Message. Ctrl-D (linux) or Ctrl-Z (windows) to save it.")
    client_response = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        client_response.append(line)
    client_response = "\r\n".join(client_response)

    if client_response.find("BEGIN PGP MESSAGE") > 0 and client_response.find("END PGP MESSAGE") > 0:
        # In decrypted message steht dann der Dateiname oder der Link von dem User.
        decrypted_message = qrm.decrypt_signed_qrcode_content(client_response)
        if decrypted_message and qrm.decryptobj_sender_key:
            # Speichere die Dateiliste für später... Todo... recipients müssen mitgespeichert werden.
            qrm.client_file_or_link_from_response = decrypted_message
            # Kann verwendet werden.
            # qrm.decryptobj_sender_key = qrm.cryptobj.last_key_used_for_signature
            #
            # Angeforderte Datei und Signatur des Anforderers nun bekannt
            return qrm.client_file_or_link_from_response
        else:
            print("Error: no decrypted signed message available, so no files or links available")
    else:
        print("Could not find BEGIN PGP MESSAGE or END PGP MESSAGE in the pasted string")

def menue_v2_servermodus_datei_senden(qrm):  # Menüpunkt 4
    if not qrm.cryptobj.get_recipients():
        print("Keine Empfänger vorhanden! Gehe ins entsprechende Menü")
        menue_v2_client_oder_server_empfaenger_auswaehlen(qrm)
    else:
        # Alle Dateien beinhaltet alle Dateien die lokal in dem entsprechenden Verzeichnis vorhanden sind.
        alle_dateien = qrm.rebuild_filelist()  # Aktuellsten Stand holen!
        if alle_dateien:  # Weiter geht es nur, wenn das Dateiarray nicht leer ist.
            menue_v2_servermodus_datei_senden_wenn_dateien_vorhanden(qrm, alle_dateien)
        else:
            print("Bitte Dateien im Verzeichnis ablegen: " + qrm.cryptobj.get_files_outgoing_available_for_encryption())

def menue_v2_servermodus_datei_senden_wenn_dateien_vorhanden(qrm, alle_dateien):
    while True:
        print("")
        print("Nr | Dateiname")
        print("---------------")
        for nummer, dateiname in enumerate(alle_dateien):
            print(str(nummer).zfill(2) + "   " + dateiname)
        print("Die Datei wird für folgende Empfänger verschlüsselt")
        print(qrm.cryptobj.get_recipients())
        print("")
        print("Aktuell liegen folgende Anforderungen von Clients vor (Client Response)")
        print("Schlüssel        |  Datei ")
        print(qrm.decryptobj_sender_key + "    " + qrm.client_file_or_link_from_response)
        print("")
        print("77) Empfänger zurücksetzen")
        print("88) Für die Übernahme der aktuellen Anforderers.")
        print("89) Erst 77) dann 88) Übernahme der aktuellen Anforderers dann -> Enkodieren der entsprechenden Datei.")
        eingabe = input("Welche Datei soll verschlüsselt werden? Bitte Nummer eingeben: (99 zum Beenden der Eingabe) ")
        try:
            eingabe = int(eingabe.strip())
        except ValueError:  # Kein Int -> nochmal von vorne!
            print("Bitte eine gültige Nummer eingeben.")
        if eingabe == 77:
            qrm.cryptobj.reset_recipients()
        if eingabe == 88:
            qrm.cryptobj.add_recipient(qrm.decryptobj_sender_key)
        if eingabe == 89:  # Empfänger zurücksetzen, Empfänger setzen, Mit Dateiauswahl in das nächste Menü.
            qrm.cryptobj.reset_recipients()
            qrm.cryptobj.add_recipient(qrm.decryptobj_sender_key)
            menue_v2_servermodus_datei_senden_mit_dateiauswahl(qrm, qrm.client_file_or_link_from_response)
        if eingabe == 99:
            break
        elif 0 <= eingabe < len(alle_dateien):
            if not qrm.cryptobj.get_recipients():  # Sollten die Empfänger zurückgesetzt worden sein...
                print("Keine Empfänger vorhanden! Gehe ins entsprechende Menü")
                menue_v2_client_oder_server_empfaenger_auswaehlen(qrm)
            else:
                menue_v2_servermodus_datei_senden_mit_dateiauswahl(qrm, alle_dateien[eingabe])
        else:
            print("Bitte eine gültige Nummer eingeben.")

def find_files(base, pattern):
    """ Hilfsfunktion: Return list of files in base folder.
    Quelle: https://stackoverflow.com/questions/4296138/use-wildcard-with-os-path-isfile
    """
    return glob.glob(os.path.join(base, pattern))

def menue_v2_servermodus_datei_senden_mit_dateiauswahl(qrm: QRCodeManagement, quelldatei_auswahl: str):
    """ Erstellt aus der übergebenen Datei eine verschlüsselte Datei für alle Empfänger
    Hierbei wird geprüft, ob die Datei schon für die Empfänger schon verschlüsselt wurde.

    Falls ja, wird gefragt, ob man es noch einmal möchte. Dann ist allerdings das "Übertragung einzelner Frames" später
    nicht mehr möglich.

    Falls nein oder wenn die Datei noch nicht existiert, dann startet es die Enkodierung als Video.

    :param qrm: QRCodeManagement Objekt, mit dem man alles steuert. In qrm.cryptobj.get_recipients() sind die Empfänger
    :param quelldatei_auswahl: Quelldatei, die verschlüsselt werden soll.
    :return: Kein Rückgabewert.
    """
    print("Verschlüssel Datei " + quelldatei_auswahl + " für Empfänger" + str(qrm.cryptobj.get_recipients()))
    destination_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                    qrm.cryptobj.get_files_outgoing_already_encrypted()))

    # Im Dateinamen der Zieldatei sollen die Empfänger mit erfasst werden,
    # damit man sich die doppelte Arbeit erspart Dateien mehrfach zu entschlüsseln
    zieldateiname = quelldatei_auswahl + str(qrm.cryptobj.get_recipients()) + ".gpg"
    destination_file = os.path.join(destination_path, zieldateiname)

    # Alle Empfänger durchlaufen und schauen, ob es schon eine Datei mit dem Namen existiert
    search_found = 0

    print("Prüfe, ob Empfänger diese Datei schon einmal erhalten haben...")
    for pattern in qrm.cryptobj.get_recipients():
        # Wurde die Datei schon für den Empfänger verschlüsselt?
        if find_files(destination_path, quelldatei_auswahl + "*" + pattern + "*.gpg"):
            search_found += 1
            print(" - " + str(search_found) + ". Empfänger mit PubKey " + pattern + " in Datei " +
                  str(find_files(destination_path, quelldatei_auswahl + "*" + pattern + "*.gpg")) + " gefunden... ")

    if not os.path.exists(destination_file) and not (search_found == len(qrm.cryptobj.get_recipients())):
        print("Datei " + quelldatei_auswahl + " wird verschlüsselt...")
        ergebnis = qrm.cryptobj.encrypt_file(quelldatei_auswahl, destination_filename=zieldateiname)
    else:
        # Datei existiert im Zielordner schon für ALLE Empfänger, ggf andere Reihenfolge im Dateinamen
        print("Datei wurde schon für diese Empfänger verschlüsselt!")
        print("Möchten Sie es erneut verschlüsseln? (weil sich z.B. der Dateiinhalt geändert hat)")
        print("(Falls J, dann  kann man fehlerhafte Übertragungen der alten Datei nicht mehr korrigieren)")
        entscheide = input("Auswahl (J/j/N/n/Y/y): ")
        if entscheide.lower() == "j" or entscheide.lower() == "y":
            print("Datei " + quelldatei_auswahl + " wird erneut verschlüsselt...")
            ergebnis = qrm.cryptobj.encrypt_file(quelldatei_auswahl, destination_filename=zieldateiname)
        else:
            ergebnis = False
    if ergebnis:
        print("Datei wurde verschlüsselt... Jetzt Video per Multithreading erstellen...")
        # Wichtigster Teil des Ganzen... Videoenkodierung!
        dateiname = startup_multithreading(qrm, zieldateiname)
        qrm.last_encoded_video_filenames = dateiname  # zieldateiname
        print("Videodateien liegen hier: " + dateiname)
    else:
        print("Datei wurde NICHT (erneut) verschlüsselt...")
        # Trotzdem Dateinamen merken, damit man es einfacher hochladen kann...
        dateiname = str.strip(zieldateiname) + "*.mp4"
        qrm.last_encoded_video_filenames = dateiname
        print("(Nicht neu enkodierte) Videodateien liegen hier: " + dateiname)

def main():
    # I5 (2026): Schluessel und Passphrase nicht mehr im Code, sondern aus der Umgebung
    gnupg_signer_fingerprint = os.environ.get("QRVIDEO_SIGN_FINGERPRINT")
    gnupg_sign_key_id = [gnupg_signer_fingerprint[-16:]] if gnupg_signer_fingerprint else None
    gnupg_passphrase_for_signing = os.environ.get("QRVIDEO_PASSPHRASE")

    if (gnupg_sign_key_id is None) or \
            (gnupg_signer_fingerprint is None) or \
            (gnupg_passphrase_for_signing is None):
        print("Error: Please set QRVIDEO_SIGN_FINGERPRINT and QRVIDEO_PASSPHRASE. Exiting.")
        print("")
        sys.exit(0)
    else:
        gpg = gnupg.GPG(gpgbinary="C:\\Program Files (x86)\\GnuPG\\bin\\gpg.exe")
        result = gpg.encrypt("Test", gnupg_sign_key_id,
                             sign=gnupg_signer_fingerprint,
                             passphrase=gnupg_passphrase_for_signing)
        if not result.ok:
            print("Falsche Passphrase für den angegebenen Schlüssel übergeben! Beende Programm... ")
            sys.exit(0)

        qrm = QRCodeManagement(pubkey_server_fingerprint=gnupg_signer_fingerprint,
                               privkey_passphrase=gnupg_passphrase_for_signing)

        while True:
            menue_v2(qrm)



if __name__ == "__main__":
    main()
