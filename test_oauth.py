import unittest
import time
import jwt
import oauth_handler
import auth_config

class TestOAuthHandler(unittest.TestCase):
    def test_pkce_generation(self):
        verifier, challenge = oauth_handler.generate_pkce_pair()
        self.assertIsNotNone(verifier)
        self.assertIsNotNone(challenge)
        self.assertTrue(len(verifier) >= 43)
        self.assertTrue(len(challenge) >= 43)

    def test_generate_state(self):
        state = oauth_handler.generate_state()
        self.assertIsNotNone(state)
        self.assertEqual(len(state), 32)

    def test_build_authorize_url(self):
        verifier, challenge = oauth_handler.generate_pkce_pair()
        state = oauth_handler.generate_state()
        url = oauth_handler.build_authorize_url(
            client_id="test_client",
            redirect_uri="http://localhost:5000/callback",
            code_challenge=challenge,
            state=state
        )
        self.assertIn("response_type=code", url)
        self.assertIn("client_id=test_client", url)
        self.assertIn("code_challenge=" + challenge, url)
        self.assertIn("state=" + state, url)

    def test_jwt_minting_and_verification(self):
        user_id = "12345"
        username = "TestUser"
        access_token = "access_xyz"
        refresh_token = "refresh_abc"
        expires_at = time.time() + 3600

        token = oauth_handler.generate_jwt(
            user_id=user_id,
            username=username,
            access_token=access_token,
            refresh_token=refresh_token,
            wiki_token_expires_at=expires_at
        )

        self.assertIsNotNone(token)
        
        # Verify it
        payload = oauth_handler.verify_jwt(token)
        self.assertEqual(payload["sub"], user_id)
        self.assertEqual(payload["username"], username)
        self.assertEqual(payload["access_token"], access_token)
        self.assertEqual(payload["refresh_token"], refresh_token)
        self.assertAlmostEqual(payload["wiki_token_expires_at"], expires_at, places=2)

    def test_jwt_expiry(self):
        # We can temporarily mock JWT_EXPIRATION_SECS to a negative value or test is_token_expired
        self.assertTrue(oauth_handler.is_token_expired(time.time() - 10))
        self.assertFalse(oauth_handler.is_token_expired(time.time() + 100))

if __name__ == "__main__":
    unittest.main()
