#!/usr/bin/env python3

import mysql.connector

ROOT_USER = "root"
PORT = 3306

class MariaDB():
      def __init__(self,host,username,password):
            self.host = host
            self.username = username
            self.password = password

      def is_ready(self):
        try:
          mydb = mysql.connector.connect(
                    host=HOST,
                    user=USER,
                    password=PASSWORD
                  )    
          return True
        except Exception as e:
          return False

      