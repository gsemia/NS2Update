import urllib2, subprocess, sys, os, time, argparse, psutil
from threading import Thread
from Queue import Queue, Empty
from time import strftime
from SourceQuery import SourceQuery
from ns2config import NS2Config
from ns2rcon import NS2Rcon

def enqueue_output(out, queue, logFile, chatqueue):
	for line in iter(out.readline,''):
		line = line.rstrip("\r\n")
		queue.put(line)
		logFile.write(line+"\n")
		logFile.flush()
		#Chat All - devicenull: "test"
		#Chat Team 0 - devicenull: "test2"
		if line.startswith("Chat All") or line.startswith("Chat Team"):
			chatqueue.put(line)
	out.close()

class NS2Update:
	# Handle to the process where the server is running
	serverProc = None
	# outputThread will be a seperate thread that is spawned to grab all the output from the server
	# It will push it all into outputQueue, as well as to serverLogFile
	# outputQueue is currently unused, but will ultimately allow actions to be taken based on log events
	outputQueue = None
	chatQueue = None
	outputThread = None
	serverLogFile = None
	# Time of the last update check
	lastCheck = 0
	# How often we should check for updates.  This is set by the update server
	checkDelay = 300
	# What URL to grab the latest version from.  Ideally we would grab this from the CDR on the fly
	# but that's not terribly resource-friendly to do
	versionURL = "http://ns2update.devicenull.org/ns2update/ns2version.txt"
	# What version of the software is the server currently running
	currentVersion = 0
	# What arguments should we pass to the server on startup
	serverArgs = ''
	# Is the server empty or not?
	serverEmptyCount = 0
	# Store the time we last started the server
	lastStart = 0
	# Should we disable update checking?
	noUpdateCheck = False
	# This gets set to true when the server has had players on it
	hasHadPlayers = False
	# Store the last stats values
	lastCPU = 0
	lastMemory = 0
	lastTickrate = 0

	def __init__(self, logger, UpdateToolPath, serverDirectory, serverArgs):
		self.logger = logger
		self.serverDir = serverDirectory
		self.serverArgs = serverArgs
		self.serverConfig = NS2Config(serverArgs,serverDirectory)
		self.serverRcon = NS2Rcon(self,serverDirectory)

		self.restartWhenEmpty = False
		self.noUpdateCheck = False

		argParser = argparse.ArgumentParser(prog='NS2')
		argParser.add_argument('--restartwhenempty',action='store_true')
		argParser.add_argument('--noupdatecheck',action='store_true')
		try:
			parsed,otherargs = argParser.parse_known_args(serverArgs.split(' '))
			self.restartWhenEmpty = parsed.restartwhenempty
			self.noUpdateCheck = parsed.noupdatecheck
		except:
			pass

		# have to do this after we parse the command line
		self.findUpdateTool(UpdateToolPath)

		# NS2 doesn't like extra command line args (and will die if they are present)
		self.serverArgs = self.serverArgs.replace('--restartwhenempty','').replace('--noupdatecheck','')

		# Query is one port higher then join
		self.serverPort = int(self.serverConfig['port'])+1

		self.logger.info("Detected server IP as %s:%i" % (self.serverConfig['address'],self.serverPort))
		self.queryObject = SourceQuery(self.serverConfig['address'],self.serverPort)

		if self.restartWhenEmpty:
			self.logger.info("Server will be automatically restarted when empty")
		else:
			self.logger.info("Server will *NOT* be automatically restarted when empty")

		if self.serverConfig['game'].lower().find("ns2gmovrmind") != -1:
			self.getTickrate = True
			self.logger.info("NSGmOvermind detected, tickrate stats are available")
			self.logger.debug("NS2GmOvermind query: %s:%i" % (self.serverConfig['address'],self.serverPort+1))
			self.overmindQueryObject = SourceQuery(self.serverConfig['address'],self.serverPort+1)
		else:
			self.getTickrate = False
			self.logger.info("NS2GmOvermind *NOT* detected, tickrate stats unavailable")

	def findUpdateTool(self,extraPath):
		if self.noUpdateCheck:
			self.logger.info("Update checking disabled, not looking for hldsupdatetool")
			return

		paths = [ "../hldsupdatetool.exe", "hldsupdatetool.exe" ]

		if extraPath != None and extraPath != '':
			paths.append(extraPath)

		self.updatePath = ""
		for cur in paths:
			if os.path.exists(cur):
				self.updatePath = cur

		if self.updatePath == "":
			self.logger.critical("Unable to find hldsupdatetool.exe, please copy to server directory or see README")
			raise NameError("Unable to find hldsupdatetool.exe")

	def doUpdate(self):
		self.logger.info("Starting server update")

		update = subprocess.Popen("%s -command update -game naturalselection2 -dir %s" % (self.updatePath,self.serverDir))
		if update:
			while update.returncode == None:
				time.sleep(5)
				update.poll()

		self.logger.info("Server update complete!")

	def startServer(self):
		# If we are starting the server, it must be empty
		self.serverEmptyCount = 0
		self.hasHadPlayers = False
		self.lastStart = time.time()

		# Actually start the server process
		self.serverProc = subprocess.Popen("Server.exe %s" % self.serverArgs, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
		self.logger.info("Server started, pid %i version %s" % (self.serverProc.pid,self.currentVersion))

		# Open up the log file
		logName = strftime("%Y.%m.%d.%H%M.log")
		self.logger.debug("Logging to %s" % logName)
		self.serverLogFile = open("serverlogs/%s" % logName,"a")

		# Setup everything we need to capture the server output
		self.outputQueue = Queue()
		self.chatQueue = Queue()
		self.outputThread = Thread(target=enqueue_output, args=(self.serverProc.stdout, self.outputQueue, self.serverLogFile, self.chatQueue))
		self.outputThread.daemon = True
		self.outputThread.start()
		self.outputQueue.put("*** SERVER STARTED ***\n")

	def stopServer(self):
		if self.serverProc != None:
			self.logger.info("Killing server")
			self.serverProc.kill()
			self.cleanupServer()

	def cleanupServer(self):
		if self.outputThread != None:
			self.outputThread.join()
		if self.serverLogFile != None:
			self.serverLogFile.close()
		self.outputThread = None
		self.serverLogFile = None
		self.serverProc = None

	# Tickrate is currently unsupported, but adding it here is easier then modfiying rrd's later
	def recordStats(self,players,tickrate):
		if not os.path.exists("%s/rrdtool.exe" % self.serverDir):
			return

		statsFile = "%s/ns2update.rrd" % (self.serverDir)
		if not os.path.exists(statsFile):
			#os.system("\"%s/rrdtool.exe\" create \"%s\" DS:memory:GAUGE:300:0:U DS:cpu:GAUGE:600:0:U DS:players:GAUGE:600:0:U DS:tickrate:GAUGE:600:0:U RRA:LAST:0.5:1:2016 RRA:AVERAGE:0.5:2:2016" % (self.serverDir,statsFile))
			subprocess.Popen(["%s/rrdtool.exe" % self.serverDir, "create", statsFile, "DS:memory:GAUGE:300:0:U", "DS:cpu:GAUGE:600:0:U", "DS:players:GAUGE:600:0:U", "DS:tickrate:GAUGE:600:0:U", "RRA:LAST:0.5:1:2016", "RRA:AVERAGE:0.5:2:2016"])

		p = psutil.Process(self.serverProc.pid)
		cpu = p.get_cpu_percent(interval=1.0)
		meminfo = p.get_memory_info()
		rss = meminfo[0] / 1024 / 1024

		self.logger.debug("CPU usage: %02i, memory: %04i MB, players: %02i tickrate: %02i" % (cpu, rss, players, int(tickrate)))
		self.lastCPU = cpu
		self.lastMemory = rss
		self.lastTickrate = tickrate

		#os.system("\"%s/rrdtool.exe\" update \"%s\" N:%i:%f:%i:%s" % (self.serverDir, statsFile, rss, cpu, players, tickrate))
		subprocess.Popen(["%s/rrdtool.exe" % self.serverDir, "update", statsFile, "N:%i:%f:%i:%s" % (rss, cpu, players, tickrate)])

		# Escape colons so rrdtool doesn't die
		statsFile = statsFile.replace(":","\\:")
		subprocess.Popen("\"%s/rrdtool.exe\" graph \"%s/ns2server.png\" --height 200 --width 400 --font DEFAULT:0:\"%s\"/rrdfont.ttf  DEF:memory=\"%s\":memory:LAST CDEF:memorydisp=memory,10,/ DEF:cpu=\"%s\":cpu:LAST DEF:players=\"%s\":players:LAST DEF:tickrate=\"%s\":tickrate:LAST AREA:cpu#00FF00:\"%% CPU Usage\"  LINE:memorydisp#FF0000:\"Memory usage (MB/10)\" LINE1:players#0000FF:\"Players\" LINE1:tickrate#000000:\"Tickrate\"" % (self.serverDir, self.serverDir, self.serverDir, statsFile, statsFile, statsFile, statsFile),stdout=subprocess.PIPE).wait()

	def think(self):
		if not self.noUpdateCheck and time.time() - self.lastCheck > self.checkDelay:
			self.logger.debug("Checking for server update...")
			data = urllib2.urlopen(self.versionURL)

			temp = data.read(100).split(",")
			if temp[0] > 0 and temp[1] > 60:
				desiredVersion = temp[0]
				if self.checkDelay != int(temp[1]):
					self.checkDelay = int(temp[1])
					self.logger.debug("Setting update check delay to %i" % self.checkDelay)

			if desiredVersion > self.currentVersion:
				self.logger.info("Server is out of date: current: %s desired: %s" % (self.currentVersion,desiredVersion))
				if self.serverProc != None:
					self.stopServer()

				if self.currentVersion == 0:
					self.logger.info("Performing inital server update")
					self.doUpdate()
				else:
					self.doUpdate()

				self.currentVersion = desiredVersion
				self.startServer()
			self.lastCheck = time.time()

		if self.serverProc == None:
			self.startServer()

		self.serverProc.poll()
		if self.serverProc.returncode != None:
			self.logger.critical("Server has died, restarting!")
			self.cleanupServer()
			self.startServer()

		currentPlayers = 0
		tickrate = 0
		# Don't check the server for 10s after it started (avoids issues with query not responding during startup)
		if time.time()-self.lastStart > 10:
			# If we are going to attempt to restart the server when it's empty, we need to query it..
			try:
				details = self.queryObject.info()
				currentPlayers = details['numplayers']

				if self.restartWhenEmpty:

					if details['numplayers'] == 0:
						self.serverEmptyCount += 1
					else:
						self.serverEmptyCount = 0
						self.hasHadPlayers = True

					if self.serverEmptyCount > 5 and self.hasHadPlayers:
						self.logger.info("Server now empty, restarting")
						self.stopServer()
						time.sleep(1)
						self.startServer()
			except IOError:
				pass

			try:
				if self.getTickrate:
					rules = self.overmindQueryObject.rules()
					tickrate = rules['netstat_tickrate']
			except IOError:
				pass

		self.recordStats(currentPlayers,tickrate)

		# Use this to read console output without blocking
		#try:
		#	while 1==1:
		#		line = outQueue.get_nowait()
		#except Empty:
		#	pass

	def sendCommand(self,command):
		print "Sending command: %s" % command
		self.serverProc.stdin.write("%s\r\n" % command)