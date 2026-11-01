from __future__ import print_function
import numpy
import imageio
import pyzbar.pyzbar as pyzbar
from pyzbar.pyzbar import ZBarSymbol
import cv2
import time
import os
import sys

def split_umkehrfunktion(array, nrows, ncols):
    """ Funktioniert aktuell nur für Arrays, welche 2D als
    Zieldimension besitzen. Zusätzlich muss jede Zieldimension
    später identisch sein. Die Funktion gilt also nur für
    den POC, welcher quadratische QR Codes korrigiert.
      """
    array = array.reshape(int(array.shape[0] ** 0.5),
                          int(array.shape[0] ** 0.5), nrows, ncols)
    array = array.swapaxes(1, 2)
    return array.reshape(array.shape[0] * nrows,
                         array.shape[0] * nrows)

def split(array, nrows, ncols):
    """Split a matrix into sub-matrices.
    Quelle https://stackoverflow.com/
    questions/11105375/
    how-to-split-a-matrix-into-4-blocks-using-numpy """
    r, h = array.shape
    return (array.reshape(h // nrows, nrows, -1, ncols)
            .swapaxes(1, 2)
            .reshape(-1, nrows, ncols))

def youtube_qrcode_korrektur(youtube_frame_qrcode):
    # den QRCode unterteilen in einzelne Module von 2x2 Pixeln
    modules_qrcode_teil_youtube = split(youtube_frame_qrcode, 2, 2)
    # modules_qrcode_teil_original = split(original_frame_qrcode, 2, 2)

    # # Ein Array vordefinieren, welches die gleiche Größe wie der Modules QR-Code Teil besitzt
    # meinarray = numpy.zeros((modules_qrcode_teil_original.shape[0], 2), dtype=numpy.int)
    # # durchlaufe alle einzelnen MOdule (177x177 = 31329 Stück), wenn alles richtig läuft)
    # for i in range(modules_qrcode_teil_original.shape[0]):  # Todo diese Schleife auflösen!mit mean und axis!
    #     # Durchschnittswert ist ein Float. Zwei Stellen genügen. Geschwindigkeit erhöht da int anstatt float
    #     meinarray[i][0] = int(modules_qrcode_teil_youtube[i].mean()*100)
    #     meinarray[i][1] = int(modules_qrcode_teil_original[i].mean()*100)
    #
    # # Array sortieren mit Mittelwerten (Spalte1) und dazugehörigen Originalwerten (Spalte 2)
    # # Sortieren nach den Werten in der ersten Achse (also nach den Mittelwerten des YouTube Anteils)
    # sortiert = numpy.sort(meinarray, axis=0)
    # print(sortiert[:, 1])
    # # Gibt die Indexpositionen in sortiert heraus, welche
    # pivotnummern = numpy.where(sortiert == 25500)
    # print(pivotnummern)
    # print(pivotnummern[0][0])  # Erstes Element, welches vom Wert von 0 nach 25500 switched.
    # pivotnummer_fuer_index = pivotnummern[0][0]
    #
    # wert_vor_pivot = sortiert[pivotnummer_fuer_index - 1][0]
    # pivotwert = sortiert[pivotnummer_fuer_index][0]

    # # Die nächsten Zeilen werden für die Verständlichkeit gelassen:
    # # Dies ist von jedem Modul (2x2) die oberen beiden Werte zusammengefasst,
    # # dann die unteren beiden Werte des Moduls... und das über alle Module
    # durchschnittswerte_achse_zwei = numpy.mean(modules_qrcode_teil_youtube, axis=2)
    # # danach fasse ich die beiden Durchschnittswerte des Moduls zusammen zu einem
    # # Eine andere Möglichkeit in einem Schritt habe ich einfach nicht gefunden, ohne die gesamte Matrix
    # # zu rollieren und Achsen zu switchen. Verständlichkeit geht hier vor Rechengeschwindigkeit
    # # Außerdem funktioniert dies NUR bei 2x2 Modulen. Für den POC reicht es, denn kleiner oder größer ist nicht
    # # empfehlenswert auf grund von Erkennungsgenauigkeit oder Informationsdichtenverlust...
    # durchschnittswerte_der_module = numpy.mean(durchschnittswerte_achse_zwei, axis=1)
    # print(numpy.mean(numpy.mean(modules_qrcode_teil_youtube, axis=2), axis=1))
    durchschnittswerte_der_module = numpy.mean(numpy.mean(modules_qrcode_teil_youtube, axis=2), axis=1)

    # Todo rausnehmen des kommentarblocks
    # print(numpy.array_equal(durchschnittswerte_der_module,
    #                         numpy.mean(numpy.mean(modules_qrcode_teil_youtube, axis=2), axis=1)))
    # print(numpy.array_equal(durchschnittswerte_der_module,meinarray[:, 0] / 100))
    # print("meinarray[:][0]", meinarray[:, 0] / 100)
    # print("durchschnittswert bei youtube qr code", numpy.mean(youtube_frame_qrcode))

    # 128 ist der erste Wert ab dem zu weiß korrigiert wird
    # Selbst wenn ein anderer Pivotwert genommen wird (z.B. 120 oder 140) so ist die Anzahl der falsch korrigierten
    # Elemente klein. (eventuell sogar kleiner)
    # Bei korrekt enkodierten QRCode wird über das Prüfen verschiedener Masken mit nachfolgender Penalty (Strafwerten)
    # die Anzahl der Schwarzen und Weißen Module so gewählt, dass eine Maske bevorzugt wird, bei denen die Anzahl
    # der Schwarzen und Weißen Module möglichst gleich sind und gewissen Formationen nicht vorkommen.
    # Desweiteren werden ungefähr 30 Module FALSCH korrigiert. Durch die ECC von 7% und einem dann vorliegenden
    # Fehlerwert von ca 0,1 % (33 / 31329), welche über die Menge der QR Codes kaum schwankt,
    # sind die falsch kodierten BITS vernachlässigbar klein.
    # Durch die Korrektor in eindeutige Schwarz und Weißwerte erhält der Decoder eine vereinfachte Entscheidung
    # und muss nicht selbst korrigierend eingreifen (was laut meines "Verfahrens") wesentlcih stabiler und korrekter
    # arbeitet. Der Grund hierfür liegt darin, dass hier nur YouTube" mit seiner unbekannten Anwendung der Codecs
    # als Fehlerquelle herausgerechnet werden muss und nicht zusätzlich "Schiefstellungen" des QR Codes
    # Leider ist pyzbar der einzige Open Source QRCode Leser, welcher die Erkennungsgenauigkeit der Modulversrion 40
    # über eine große Anzahl an QR Codes beibehalten kann.
    pivotwert = 12800

    # Die Indexpositionen sind jeweils die Arrayindizes, welche kleiner bzw größer gleich dem Pivotwert sind.
    # Dieses wird vorbereitend benötigt, um die Schwarz und Weißwerte zu setzen.
    indexpositionen_schwarz_nachher = numpy.where(durchschnittswerte_der_module < (pivotwert / 100))
    indexpositionen_weiss_nachher = numpy.where(durchschnittswerte_der_module >= (pivotwert / 100))

    # Hier findet die endgültige "Korrektur" des YouTube QR Codes statt (inkl. 0,1% Fehler bei Zuweisung, was egal ist)
    modules_qrcode_teil_youtube[indexpositionen_schwarz_nachher[0]] = 0
    modules_qrcode_teil_youtube[indexpositionen_weiss_nachher[0]] = 255

    # SETZE HIER NOCH DIE FINDER PATTERN!

    # # Der nächste Kommentarblock bleibt aus Verstädnisgründen stehen:
    # # Vergleicht die Pixel der beiden 2D Arrays (YouTube korrigiert und Original) und gibt die Anzahl der
    # # falschen Module aus. Ein Modul besteht aus 2x2 = 4 Pixeln
    # # Der boolsche Operator zwischen beiden numpy Array bewirkt ein Elementweises Vergleichen
    # # True wird als 1 interpretiert, weshalb die Summe exakt das wiedergibt, was man benötigt um es zu bewerten.
    # # Gibt also die Anzahl der falschen Module durch vergleich von Original mit korrigiertem YouTube aus.
    # anzahl_falscher_module = (modules_qrcode_teil_original != modules_qrcode_teil_youtube).sum() // 4
    # print("Anzahl falscher Module                   : " + str(anzahl_falscher_module))
    # print("Prozentualer Gesamtanteil falscher Module: " + str(anzahl_falscher_module * 100 / 31329))

    # Hiermit wird die per split() bearbeitete QR Code wieder in die korrekte Form umgewandelt.
    return split_umkehrfunktion(modules_qrcode_teil_youtube, 2, 2)

def fuege_weissen_rand_hinzu(pure_qrcode):
    """ Diese Funktion nimmt den QRCode ohne Rand und umgibt ihn mit einem.
    Der weiße Rand wurde vorher entfernt, um Platz im Frame zu sparen und da ansonsten keine drei Reihen
    untereinander gepasst hätten


    :param pure_qrcode: numpy array mit shape(352,352)
    :return: numpy array mit shape(352+8+8,352+8+8)
    """
    platz_fuer_white_space = 8
    leer_oben_und_unten = numpy.full((platz_fuer_white_space, pure_qrcode.shape[1]), 255, dtype=numpy.uint8)
    pure_qrcode = numpy.vstack((leer_oben_und_unten, pure_qrcode, leer_oben_und_unten))
    leer_links_und_rechts = numpy.full((pure_qrcode.shape[0], platz_fuer_white_space), 255, dtype=numpy.uint8)
    return numpy.hstack((leer_links_und_rechts, pure_qrcode, leer_links_und_rechts))

def get_corrected_frame_qr_codes(youtube_frame):
    """ Diese Funktion nimmt den übergebeneen Frame mit 1920x1080 Pixeln und schneidet die 15 QRCodes aus
    Man kann dies natürlich auch dynamisch gestalten und QRCodes Suchen, aber für den POC reicht es.
    (Außerdem ist es schnell)

    Die ausgeschnittenen QRCodes werden dann an eine Optimierungsfunktion übergeben, bei der die Module in Grautönen
    in Schwarz oder Weisse Module übersetzt werden. Es entstehen hierbei falsche Zuweisungen auf Grund der
    Kantenglättung, aber es ist überschaubar gering... (ca 0,1% -0,2% Fehlerquote and falsch übersetzten Pixeln)
    Zusätzlich werden die QRCodes mit einem weißen Rand umgeben, damit diese dann direkt  mit pyzbar analysiert werden
    können!

    :param youtube_frame: numpy array mit den Abmessungen 1080 Zeilen und 1920 Spalten
    :return: numpy array mit 15 optimierten QRCodes von je 354x354 Elementen, also vom Shape (15, 354, 354)
    """

    if len(youtube_frame.shape) == 3:
        # https://imageio.readthedocs.io/en/stable/examples.html#convert-a-movie
        # Bild muss von 3D (Farbig, dritte Dimension = RGB) nach Graustufen 2D konvertiert werden.
        # im = im[:, :, 1]
        # vorher (1080, 1920, 3), danach (1080, 1920)
        youtube_frame = youtube_frame[:, :, 1]  # In Graustufen umwandeln nur Helligkeitsebene berücksichtigen.
    assert len(youtube_frame.shape) == 2, \
        "der übergebene Frame hat nicht 2 oder 3 Dimensionen, sondern Folgende: " + str(youtube_frame.shape)

    # Korrektur des QR Codes innerhalb eines Frames von per YouTube Videos enkodierten Videos, welche
    # sonst nicht durch pyzbar zu dekodierten wären.
    # Grund hierfür ist unter anderem das Antialiasing / Kantenglättung, die beim kodierten mit x264 codec
    # durchgeführt wird. Es gibt zwar Optionen, um beim Kodieren gewissen x264 parameter zu setzen, aber
    # es ist nicht unbedingt sinnvoll, denn YouTube enkodiert selbst immer neu. Der bessere Weg ist also,
    # wenn man die YouTube Fehler rausrechnet. (siehe auch funktion write_video_file_segment)

    # Diese Funktion könnte man in pyzbar integrieren, todo überlegen, ob ich es poste...
    # nachdem der QRCode "geradegerechnet" worden ist und in graustufen vorliegt.
    # qrcode_teil_youtube = youtube_qrcode_korrektur(qrcode_teil_youtube)

    """ Spaltenindizes/QRCodegrenzen VON-BIS (Differenz immer 365 = doppelte maximale Modulgröße von 177)
    SPALTE 0   1    - 355
    SPALTE 1   363  - 717
    SPALTE 2   725  - 1079
    SPALTE 3   1087 - 1441
    SPALTE 4   1449 - 1803
    """

    """ Zeilenindizes/QRCodegrenzen VON-BIS (Differenz immer 365 = doppelte maximale Modulgröße von 177)
    ZEILE 0   1    - 355
    ZEILE 1   363  - 717
    ZEILE 2   725  - 1079
    """
    qr00_bis_qr04_idx_zeile_start = 1
    qr00_bis_qr04_idx_zeile_ende = 355
    qr05_bis_qr09_idx_zeile_start = 363
    qr05_bis_qr09_idx_zeile_ende = 717
    qr10_bis_qr14_idx_zeile_start = 725
    qr00_bis_qr14_idx_zeile_ende = 1079

    qr00_05_10_idx_spalte_start = 1
    qr01_05_10_idx_spalte_ende = 355
    qr01_06_11_idx_spalte_start = 363
    qr01_06_11_idx_spalte_ende = 717
    qr02_07_12_idx_spalte_start = 725
    qr02_07_12_idx_spalte_ende = 1079
    qr03_08_13_idx_spalte_start = 1087
    qr03_08_13_idx_spalte_ende = 1441
    qr04_09_14_idx_spalte_start = 1449
    qr04_09_14_idx_spalte_ende = 1803

    qrcode00 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                                        qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]))
    qrcode01 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                                        qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]))
    qrcode02 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                                        qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]))
    qrcode03 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                                        qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]))
    qrcode04 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                                        qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]))

    qrcode05 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                                        qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]))
    qrcode06 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                                        qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]))
    qrcode07 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                                        qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]))
    qrcode08 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                                        qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]))
    qrcode09 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                                        qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]))

    qrcode10 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                                        qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]))
    qrcode11 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                                        qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]))
    qrcode12 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                                        qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]))
    qrcode13 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                                        qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]))
    qrcode14 = fuege_weissen_rand_hinzu(youtube_qrcode_korrektur(youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                                        qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]))

    fuenfzehn_qr_codes = numpy.array(
        [qrcode00, qrcode01, qrcode02, qrcode03, qrcode04, qrcode05, qrcode06, qrcode07, qrcode08, qrcode09, qrcode10,
         qrcode11, qrcode12, qrcode13, qrcode14])

    return fuenfzehn_qr_codes

def image_enhancer(img, resizefactor=1.0, schaerfen=True, umwandeln_in_sw=True):
    """ Diese Funktion wird nicht verwendet, da ein "Enhancen" eines Bildes nicht
    zwangsweise zu guten Ergebnissen führt. Ein Enhancen führte beim POC zu keinen optimalen
    Ergebnissen, was bedeutet, dass auch nach dem Verbessern QR Codes nicht dekodierbar waren.
    Dies ist natürlich nicht akzeptabel und es wurde die manuelle Korrekturfunktion
    youtube_qrcode_korrektur() geschrieben
    """

    #
    # Quelle: https://github.com/daedalus/QRCodeMassDecoder/blob/master/QRMD.py
    # Groesse anpassen
    img = cv2.resize(img, None, fx=resizefactor, fy=resizefactor, interpolation=cv2.INTER_LINEAR)  # Das geht noch!

    # Schärfen
    kernel = numpy.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    if schaerfen:
        img = cv2.filter2D(img, -1, kernel)

    if umwandeln_in_sw:
        (thresh, img) = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    return img

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

def display(im, decodedobjects):
    """ wird für das Debuggen von nicht erkannten Daten in Frames benötigt.
    Display barcode and QR code location
    Quelle: https://www.learnopencv.com/barcode-and-qr-code-scanner-using-zbar-and-opencv/
    Zeichnet um den erkannten Barcode eine Umrandung.
    """
    # Loop over all decoded objects
    for decodedobject in decodedobjects:
        points = decodedobject.polygon

        # If the points do not form a quad, find convex hull
        if len(points) > 4:
            hull = cv2.convexHull(numpy.array([point for point in points], dtype=numpy.float32))
            hull = list(map(tuple, numpy.squeeze(hull)))
        else:
            hull = points

        # Number of points in the convex hull
        n = len(hull)

        # Draw the convext hull
        for j in range(0, n):
            cv2.line(im, hull[j], hull[(j + 1) % n], (255, 0, 0), 3)

    # Display results
    cv2.imshow("Results", im)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def analyze_video(source_video_filename_with_qrcodes: str, target_filename: str):
    assert os.path.exists(
        source_video_filename_with_qrcodes), "Error: analyze_video -> source_video_with_qrcodes file does " \
                                             "not exist! "
    reader = imageio.get_reader(source_video_filename_with_qrcodes)
    fps = reader.get_meta_data()['fps']  # Sollte 30.0 liefern...
    assert 30 == int(fps), "Movie has no 30 Frames per Second. Wrong Format. Please Check."

    # Benötigte Variablen
    radix64_dateiinhalt_str = ""  # Sum of all decoded QR-Code Content... hopefully nothing is missing ;-)
    sum_duration = 0  # Complete Duration for the whole process... just a debug information
    errors = 0  # Total number of errors occured. Must be 0
    failed_qr_codes = []  # Jedes Element: [Framenumber, Row, Column]

    # Iterate over frames in a movie
    # https://imageio.readthedocs.io/en/stable/examples.html
    framenumber = -1  # Initialisieren für den nicht vorkommenden Fall, dass keine Frames vorhanden sind
    for framenumber, im in enumerate(reader):
        start = time.time()  # Zeitnehmer... Todo  hinterherrausnehmen
        print("Analyze Frame number:", framenumber)

        # Hier wird der Frame and die Aufbereitungsfunktion bzw Reparaturfunktion übergeben.
        # Zurück kommen 15 QRCodes die dann direkt per pyzbar analysiert werden können
        for nummer, qrcode in enumerate(get_corrected_frame_qr_codes(im)):
            # Dekodiere den QR Codeinhalt
            decodedobjects = decode(qrcode)
            # print(decodedobjects)
            if decodedobjects:  # Wenn kein QR Code gefunden wird, ist decodedobjects = [] (also False)
                if not (nummer == 0):  # Management Code vorerst auslassen
                    # print("frame und qrcode nummer: ", framenumber, nummer)
                    radix64_dateiinhalt_str += decodedobjects[0].data.decode('UTF-8')
                    # print(decodedobjects[0].data.decode('UTF-8'))
                else:
                    # print("frame und qrcode nummer: ", framenumber, nummer, "Management-barcode wird ignoriert")
                    # print()
                    pass  # Hier kommen die Aktionen für den Management Code hin.
                    # Todo: Hier sollte die Reihenfolgenprüfung stattfinden.
                    #  d.h. es muss der verschlüsselte QR-Code entschlüsselt werden und die framenummer verglichen
                    #  werden. Diesen Frame kann man wieder anfordern.
                    #  Wesentlich sinnvoller ist es jedoch die QR-Codes aufzuteilen und auf Frames zu verteilen
                    #  Dies ist aber nicht Inhalt des POCs. Dadurch liese sich weiter die Informationsgehalt erhöhen
                    # Management QR COde kann erst einmal ignoriert werden... funktioniert aktuell auch so...
                    # später einfach implementieren... wenn man livestreaming macht oder dergleichen.
            else:
                # Wenn der Durchschnittswert ca 255 ist, dann ist es ein weißes Bild
                # Wenn nicht (einfach mal < 240) , dann Bild anzeigen...
                # Im Normalfall ist es ungefähr ausgeglichen -> ca 130.
                if numpy.mean(qrcode) < 220:  # Also Weiße Bilder ignorieren... 220 sollte ausreichend "weiß" sein
                    print("kleine katastrophe weil nicht weiß... qr code nicht erkannt" + str(framenumber) + " qrcodenummer " + str(nummer))
                    # cv2.imshow("T", qrcode)
                    # cv2.waitKey(0)
                    # cv2.destroyAllWindows()
                    if not (nummer == 0):  # Management Code auslassen
                        # Wenn es KEIN weißes Feld ist, dann ist was schief gegangen.
                        # Neuer Versuch... sollte zwar nicht mehr nötig sein, aber vor der Reparaturfunktion
                        # hat dies teilweise geholen
                        vergroesserung = 2
                        qrcode = numpy.repeat(qrcode, vergroesserung, axis=0).repeat(vergroesserung, axis=1)
                        # cv2.imshow("T", qrcode)
                        # cv2.waitKey(0)
                        # cv2.destroyAllWindows()
                        decodedobjects = decode(qrcode)
                        if decodedobjects:  # Wenn kein QR Code gefunden wird, ist decodedobjects = [] (also False)
                            radix64_dateiinhalt_str += decodedobjects[0].data.decode('UTF-8')
                        else:
                            print("grosse  katastrophe weil vergroesserter qr code nicht erkannt wird (Finder pattern?) " + str(
                                framenumber) + " qrcodenummer " + str(
                                nummer))
                            print("Problem Frame, nummer:", framenumber, nummer, qrcode.shape)
                            errors += 1  # Todo Anzahl Fehler am Schluss verwerten...
                            failed_qr_codes.append([framenumber, nummer])
                else:
                    # print("Kein Decoded Objekt, da weißer Bereich")
                    pass  # >=240 Weißwert... es handelt sich hier um einen weißen Bereich

        # print("Dauer des Frame: " + str(i), time.time() - start)
        sum_duration += time.time() - start

    print("Total duration for decoding:", sum_duration)
    print("Video duration in seconds  :", (framenumber + 1) / 30.0)
    print("Total number of errors     :", errors)
    if errors == 0:
        print("Writing file         :", target_filename)
        with open(target_filename, "w") as textdatei:
            textdatei.write(radix64_dateiinhalt_str)
        print("Finished writing file:", target_filename)
    else:
        print("Not writing the content to file, because an error occurred at the following qr-codes")
        print("Framenumber, Row, Column")

        for failed_code in failed_qr_codes:
            print(failed_code[0], failed_code[1], failed_code[2])
        print("len(failed_qr_codes)", len(failed_qr_codes))

    # Somit hat der nachfolgende Prozess die Möglichkeit die fehlerhaften QRCodes noch einmal zu senden
    return failed_qr_codes

#####################################################################################
# BESTANDTEIL DES VERGLEICHES VON ZWEI FRAMES (YOUTUBE+ORIGINAL) MIT QR CODES - START
def youtube_qrcode_zu_original_vergleich(youtube_frame_qrcode, original_frame_qrcode):
    # den QRCode unterteilen in einzelne Module von 2x2 Pixeln
    modules_qrcode_teil_youtube = split(youtube_frame_qrcode, 2, 2)
    modules_qrcode_teil_original = split(original_frame_qrcode, 2, 2)

    durchschnittswerte_der_module = numpy.mean(numpy.mean(modules_qrcode_teil_youtube, axis=2), axis=1)

    pivotwert = 12800

    # Die Indexpositionen sind jeweils die Arrayindizes, welche kleiner bzw größer gleich dem Pivotwert sind.
    # Dieses wird vorbereitend benötigt, um die Schwarz und Weißwerte zu setzen.
    indexpositionen_schwarz_nachher = numpy.where(durchschnittswerte_der_module < (pivotwert / 100))
    indexpositionen_weiss_nachher = numpy.where(durchschnittswerte_der_module >= (pivotwert / 100))

    # Hier findet die endgültige "Korrektur" des YouTube QR Codes statt (inkl. 0,1% Fehler bei Zuweisung, was egal ist)
    modules_qrcode_teil_youtube[indexpositionen_schwarz_nachher[0]] = 0
    modules_qrcode_teil_youtube[indexpositionen_weiss_nachher[0]] = 255

    # Der nächste Kommentarblock bleibt aus Verstädnisgründen stehen:
    # Vergleicht die Pixel der beiden 2D Arrays (YouTube korrigiert und Original) und gibt die Anzahl der
    # falschen Module aus. Ein Modul besteht aus 2x2 = 4 Pixeln
    # Der boolsche Operator zwischen beiden numpy Array bewirkt ein Elementweises Vergleichen
    # True wird als 1 interpretiert, weshalb die Summe exakt das wiedergibt, was man benötigt um es zu bewerten.
    # Gibt also die Anzahl der falschen Module durch vergleich von Original mit korrigiertem YouTube aus.
    anzahl_falscher_module = (modules_qrcode_teil_original != modules_qrcode_teil_youtube).sum() // 4
    # print("Anzahl falscher Module                   : " + str(anzahl_falscher_module))
    # print("Prozentualer Gesamtanteil falscher Module: " + str(anzahl_falscher_module * 100 / 31329))

    # Hiermit wird die per split() bearbeitete QR Code wieder in die korrekte Form umgewandelt.
    # return split_umkehrfunktion(modules_qrcode_teil_youtube, 2, 2)
    return anzahl_falscher_module

# BESTANDTEIL DES VERGLEICHES VON ZWEI FRAMES (YOUTUBE+ORIGINAL) MIT QR CODES
def get_corrected_frame_qr_codes_vergleich(youtube_frame, original_frame):
    """ Diese Funktion nimmt den übergebeneen Frame mit 1920x1080 Pixeln und schneidet die 15 QRCodes aus
    Man kann dies natürlich auch dynamisch gestalten und QRCodes Suchen, aber für den POC reicht es.
    (Außerdem ist es schnell)

    Die ausgeschnittenen QRCodes werden dann an eine Optimierungsfunktion übergeben, bei der die Module in Grautönen
    in Schwarz oder Weisse Module übersetzt werden. Es entstehen hierbei falsche Zuweisungen auf Grund der
    Kantenglättung, aber es ist überschaubar gering... (ca 0,1% -0,2% Fehlerquote and falsch übersetzten Pixeln)
    Zusätzlich werden die QRCodes mit einem weißen Rand umgeben, damit diese dann direkt  mit pyzbar analysiert werden
    können!

    :param youtube_frame: numpy array mit den Abmessungen 1080 Zeilen und 1920 Spalten
    :return: numpy array mit 15 optimierten QRCodes von je 354x354 Elementen, also vom Shape (15, 354, 354)
    """

    if len(youtube_frame.shape) == 3:
        # https://imageio.readthedocs.io/en/stable/examples.html#convert-a-movie
        # Bild muss von 3D (Farbig, dritte Dimension = RGB) nach Graustufen 2D konvertiert werden.
        # im = im[:, :, 1]
        # vorher (1080, 1920, 3), danach (1080, 1920)
        youtube_frame = youtube_frame[:, :, 1]  # In Graustufen umwandeln nur Helligkeitsebene berücksichtigen.
    if len(original_frame.shape) == 3:
        original_frame = original_frame[:, :, 1]
    assert len(youtube_frame.shape) == 2, \
        "der übergebene Frame hat nicht 2 oder 3 Dimensionen, sondern Folgende: " + str(youtube_frame.shape)

    # Korrektur des QR Codes innerhalb eines Frames von per YouTube Videos enkodierten Videos, welche
    # sonst nicht durch pyzbar zu dekodierten wären.
    # Grund hierfür ist unter anderem das Antialiasing / Kantenglättung, die beim kodierten mit x264 codec
    # durchgeführt wird. Es gibt zwar Optionen, um beim Kodieren gewissen x264 parameter zu setzen, aber
    # es ist nicht unbedingt sinnvoll, denn YouTube enkodiert selbst immer neu. Der bessere Weg ist also,
    # wenn man die YouTube Fehler rausrechnet. (siehe auch funktion write_video_file_segment)

    # Diese Funktion könnte man in pyzbar integrieren, todo überlegen, ob ich es poste...
    # nachdem der QRCode "geradegerechnet" worden ist und in graustufen vorliegt.
    # qrcode_teil_youtube = youtube_qrcode_korrektur(qrcode_teil_youtube)

    """ Spaltenindizes/QRCodegrenzen VON-BIS (Differenz immer 365 = doppelte maximale Modulgröße von 177)
    SPALTE 0   1    - 355
    SPALTE 1   363  - 717
    SPALTE 2   725  - 1079
    SPALTE 3   1087 - 1441
    SPALTE 4   1449 - 1803
    """

    """ Zeilenindizes/QRCodegrenzen VON-BIS (Differenz immer 365 = doppelte maximale Modulgröße von 177)
    ZEILE 0   1    - 355
    ZEILE 1   363  - 717
    ZEILE 2   725  - 1079
    """
    qr00_bis_qr04_idx_zeile_start = 1
    qr00_bis_qr04_idx_zeile_ende = 355
    qr05_bis_qr09_idx_zeile_start = 363
    qr05_bis_qr09_idx_zeile_ende = 717
    qr10_bis_qr14_idx_zeile_start = 725
    qr00_bis_qr14_idx_zeile_ende = 1079

    qr00_05_10_idx_spalte_start = 1
    qr01_05_10_idx_spalte_ende = 355
    qr01_06_11_idx_spalte_start = 363
    qr01_06_11_idx_spalte_ende = 717
    qr02_07_12_idx_spalte_start = 725
    qr02_07_12_idx_spalte_ende = 1079
    qr03_08_13_idx_spalte_start = 1087
    qr03_08_13_idx_spalte_ende = 1441
    qr04_09_14_idx_spalte_start = 1449
    qr04_09_14_idx_spalte_ende = 1803

    original_qrcode00 = original_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                        qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]
    original_qrcode01 = original_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                        qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]
    original_qrcode02 = original_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                        qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]
    original_qrcode03 = original_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                        qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]
    original_qrcode04 = original_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                        qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]

    original_qrcode05 = original_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                        qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]
    original_qrcode06 = original_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                        qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]
    original_qrcode07 = original_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                        qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]
    original_qrcode08 = original_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                        qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]
    original_qrcode09 = original_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                        qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]

    original_qrcode10 = original_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                        qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]
    original_qrcode11 = original_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                        qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]
    original_qrcode12 = original_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                        qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]
    original_qrcode13 = original_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                        qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]
    original_qrcode14 = original_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                        qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]

    youtube_qrcode00 = youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                       qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]
    youtube_qrcode01 = youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                       qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]
    youtube_qrcode02 = youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                       qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]
    youtube_qrcode03 = youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                       qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]
    youtube_qrcode04 = youtube_frame[qr00_bis_qr04_idx_zeile_start:qr00_bis_qr04_idx_zeile_ende,
                       qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]

    youtube_qrcode05 = youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                       qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]
    youtube_qrcode06 = youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                       qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]
    youtube_qrcode07 = youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                       qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]
    youtube_qrcode08 = youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                       qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]
    youtube_qrcode09 = youtube_frame[qr05_bis_qr09_idx_zeile_start:qr05_bis_qr09_idx_zeile_ende,
                       qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]

    youtube_qrcode10 = youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                       qr00_05_10_idx_spalte_start:qr01_05_10_idx_spalte_ende]
    youtube_qrcode11 = youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                       qr01_06_11_idx_spalte_start:qr01_06_11_idx_spalte_ende]
    youtube_qrcode12 = youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                       qr02_07_12_idx_spalte_start:qr02_07_12_idx_spalte_ende]
    youtube_qrcode13 = youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                       qr03_08_13_idx_spalte_start:qr03_08_13_idx_spalte_ende]
    youtube_qrcode14 = youtube_frame[qr10_bis_qr14_idx_zeile_start:qr00_bis_qr14_idx_zeile_ende,
                       qr04_09_14_idx_spalte_start:qr04_09_14_idx_spalte_ende]

    # Zurückgeliefert wird Anzahl der Bitfehler pro QR Code als Vergleich von original zu youtube.
    # Pro Frame dann die Anzahl der falschen Module pro QR Code an jeweiliger Position speichern.
    anzahl_falscher_module = numpy.zeros((15), dtype="uint8")
    anzahl_falscher_module[0] = youtube_qrcode_zu_original_vergleich(youtube_qrcode00, original_qrcode00)
    anzahl_falscher_module[1] = youtube_qrcode_zu_original_vergleich(youtube_qrcode01, original_qrcode01)
    anzahl_falscher_module[2] = youtube_qrcode_zu_original_vergleich(youtube_qrcode02, original_qrcode02)
    anzahl_falscher_module[3] = youtube_qrcode_zu_original_vergleich(youtube_qrcode03, original_qrcode03)
    anzahl_falscher_module[4] = youtube_qrcode_zu_original_vergleich(youtube_qrcode04, original_qrcode04)
    anzahl_falscher_module[5] = youtube_qrcode_zu_original_vergleich(youtube_qrcode05, original_qrcode05)
    anzahl_falscher_module[6] = youtube_qrcode_zu_original_vergleich(youtube_qrcode06, original_qrcode06)
    anzahl_falscher_module[7] = youtube_qrcode_zu_original_vergleich(youtube_qrcode07, original_qrcode07)
    anzahl_falscher_module[8] = youtube_qrcode_zu_original_vergleich(youtube_qrcode08, original_qrcode08)
    anzahl_falscher_module[9] = youtube_qrcode_zu_original_vergleich(youtube_qrcode09, original_qrcode09)
    anzahl_falscher_module[10] = youtube_qrcode_zu_original_vergleich(youtube_qrcode10, original_qrcode10)
    anzahl_falscher_module[11] = youtube_qrcode_zu_original_vergleich(youtube_qrcode11, original_qrcode11)
    anzahl_falscher_module[12] = youtube_qrcode_zu_original_vergleich(youtube_qrcode12, original_qrcode12)
    anzahl_falscher_module[13] = youtube_qrcode_zu_original_vergleich(youtube_qrcode13, original_qrcode13)
    anzahl_falscher_module[14] = youtube_qrcode_zu_original_vergleich(youtube_qrcode14, original_qrcode14)

    return anzahl_falscher_module

# BESTANDTEIL DES VERGLEICHES VON ZWEI FRAMES (YOUTUBE+ORIGINAL) MIT QR CODES
def analyze_video_vergleich():
    """ Hiermit können die Frames und die QR Codes darin 1:1 verglichen werden.
    Einfach die Pfade unten definieren... die Dateinamen müssen allerdings identisch sein.
    """
    from os import listdir
    from os.path import isfile, join

    pfad_original = "D:\\Thesis_temp_Vergleich Video Original zu YouTube\\BoVfcxU1L5I_1080p_VOR_UPLOAD\\"
    pfad_youtube = "D:\\Thesis_temp_Vergleich Video Original zu YouTube\\BoVfcxU1L5I_1080p_YOUTUBE\\"
    assert os.path.exists(pfad_original)
    assert os.path.exists(pfad_youtube)

    nur_dateien_original = [f for f in listdir(pfad_original) if isfile(join(pfad_original, f))]
    nur_dateien_youtube = [f for f in listdir(pfad_youtube) if isfile(join(pfad_youtube, f))]


    for num,dateiname in enumerate(nur_dateien_original):
        print(nur_dateien_original[num], nur_dateien_youtube[num])
        bild_original = imageio.imread(pfad_original + nur_dateien_original[num])
        bild_youtube = imageio.imread(pfad_youtube + nur_dateien_youtube[num])

        fehler_pro_qrcode_im_frame = get_corrected_frame_qr_codes_vergleich(bild_youtube, bild_original)
        try: gesamt_fehler_alle_frames
        except NameError: gesamt_fehler_alle_frames = fehler_pro_qrcode_im_frame
        else:
            gesamt_fehler_alle_frames = numpy.vstack((gesamt_fehler_alle_frames, fehler_pro_qrcode_im_frame))

    with numpy.printoptions(threshold=numpy.inf):
        print(gesamt_fehler_alle_frames)
    sys.exit(0)

# BESTANDTEIL DES VERGLEICHES VON ZWEI FRAMES (YOUTUBE+ORIGINAL) MIT QR CODES -  ENDE
#####################################################################################

# Main
if __name__ == '__main__':
    print("Aufruf bitte über das Hauptprogramm...")
    # source = "files_incoming_encrypted//<video-id>_1080p.mp4"
    # target = "files_incoming_encrypted//<video-id>_1080p.mp4.gpg"
    # analyze_video(source, target)

    # analyze_video_vergleich()  # Vergleichsfunktion
