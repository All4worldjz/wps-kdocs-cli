import Fastify from 'fastify';
import cors from '@fastify/cors';
import dotenv from 'dotenv';

import userRoutes from './routes/user.js';
import documentRoutes from './routes/document.js';
import materialRoutes from './routes/material.js';
import articleRoutes from './routes/article.js';
import writingStyleRoutes from './routes/writingStyle.js';
import layoutAndTasksRoutes from './routes/layoutAndTasks.js';

dotenv.config();

const fastify = Fastify({
  logger: true
});

// Configure CORS to allow frontend communication
await fastify.register(cors, {
  origin: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'Geekseek-Authorization', 'Geekseek-Language']
});

// Register routes
fastify.register(userRoutes);
fastify.register(documentRoutes);
fastify.register(materialRoutes);
fastify.register(articleRoutes);
fastify.register(writingStyleRoutes);
fastify.register(layoutAndTasksRoutes);

// Add health check route
fastify.get('/health', async (request, reply) => {
  return { status: 'OK', timestamp: new Date().toISOString() };
});

const start = async () => {
  try {
    const port = process.env.PORT || 8080;
    const address = await fastify.listen({ port, host: '127.0.0.1' });
    console.log(`Server listening on ${address}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
