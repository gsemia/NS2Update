import json, cherrypy
from authcontroller import require

class ServerInfo:
	def __init__(self, webserver, updater):
		self.webserver = webserver
		self.updater = updater

	@cherrypy.expose
	def index(self):
		return "Oops!  You want /general"

	@cherrypy.expose
	def general(self):
		cherrypy.response.headers['content-type'] = 'application/json'
		try:
			details = self.updater.queryObject.info()

			return json.dumps({
				'current_players': details['numplayers']
				,'max_players': details['maxplayers']
				,'server_name': details['hostname']
				,'map': details['map']
			})
		except:
			return '{}'